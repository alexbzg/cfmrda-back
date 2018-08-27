#!/usr/bin/python3
#coding=utf-8
import asyncio
import json
import logging
import time

import pytest
from aiohttp.test_utils import make_mocked_request
import requests

from srv import CfmRdaServer
import recaptcha
import send_email
from common import site_conf

CONF = site_conf()
WEB_ADDRESS = CONF.get('web', 'address')
API_URI = WEB_ADDRESS + '/aiohttp'

token = None

@pytest.fixture(autouse=True)
def replace_recaptcha(monkeypatch):

    @asyncio.coroutine
    def mock_recaptcha(val):
        return val == 'mock_true'

    def mock_send_email(**kwargs):
        return True
        
    monkeypatch.setattr(recaptcha, 'check_recaptcha', mock_recaptcha)
    monkeypatch.setattr(send_email, 'send_email', mock_send_email)

@pytest.fixture(scope="session")
def cfm_rda_server():
    return CfmRdaServer(asyncio.get_event_loop())


class MockPayload():

    def __init__(self, data):
        self._bytes = json.dumps(data).encode()

    @asyncio.coroutine
    def readany(self):
        rsp = self._bytes
        self._bytes = b''
        return rsp

def test_register(cfm_rda_server):

    _data = {'callsign': 'R7CLL',\
            'password': 'rytqcypz',\
            'mode': 'register',\
            'recaptcha': 'mock_true',\
            'email': 'welcome@masterslav.ru'}

    def create_request(method, url, data=None):
        req = make_mocked_request(method, url)
        if data:
            req._payload = MockPayload(data)
        #req._client_max_size = 0
        return req

    @asyncio.coroutine
    def do_test():

        yield from asyncio.sleep(0.1)
        clean_user = False

        try:

            method = 'POST'
            url = '/aiohttp/login'

            logging.debug('Creating wrong user')
            rsp = yield from cfm_rda_server.login_hndlr(create_request(method, url, _data))
            logging.debug(rsp.text + '\n')
            assert rsp.status == 400

            logging.debug('Creating invalid user')
            del _data['callsign']
            rsp = yield from cfm_rda_server.login_hndlr(create_request(method, url, _data))
            logging.debug(rsp.text + '\n')
            assert rsp.status == 400

            logging.debug('Creating user with invalid captcha')
            _data['callsign'] = 'R7CL'
            _data['recaptcha'] = 'lawecnhjasmknd.c/lasfhewuo;fh'
            rsp = yield from cfm_rda_server.login_hndlr(create_request(method, url, _data))
            logging.debug(rsp.text + '\n')
            assert rsp.status == 400

            logging.debug('Creating user')
            _data['recaptcha'] = 'mock_true'
            rsp = yield from cfm_rda_server.login_hndlr(create_request(method, url, _data))
            logging.debug(rsp.text + '\n')
            assert rsp.status == 200
            clean_user = True

            logging.debug('Creating dublicate user')
            rsp = yield from cfm_rda_server.login_hndlr(create_request(method, url, _data))
            logging.debug(rsp.text + '\n')
            assert rsp.status == 400        

            logging.debug('Test login with no confirmed email')
            _data['mode'] = 'login'
            rsp = yield from cfm_rda_server.login_hndlr(create_request(method, url, _data))
            logging.debug(rsp.text + '\n')
            assert rsp.status == 400        


            method = 'GET'

            logging.debug('Confirm email with no callsign token')
            token = cfm_rda_server.create_token({'time': time.time()})
            url = '/aiohttp/confirm_emai?token=' + token
            rsp = yield from cfm_rda_server.cfm_email_hndlr(create_request(method, url))
            logging.debug(rsp.text + '\n')
            assert rsp.status == 400        

            logging.debug('Confirm email obsolete token')
            token = cfm_rda_server.create_token({'time': time.time() - 60 * 70, 'callsign': 'R7CL'})
            url = '/aiohttp/confirm_emai?token=' + token
            rsp = yield from cfm_rda_server.cfm_email_hndlr(create_request(method, url))
            logging.debug(rsp.text + '\n')
            assert rsp.status == 400        

            logging.debug('Confirm email')
            token = cfm_rda_server.create_token({'time': time.time(), 'callsign': 'R7CL'})
            url = '/aiohttp/confirm_email?token=' + token
            rsp = yield from cfm_rda_server.cfm_email_hndlr(create_request(method, url))
            logging.debug(rsp.text + '\n')
            assert rsp.status == 200

            method = 'POST'

            logging.debug('Test login')
            _data['mode'] = 'login'
            rsp = yield from cfm_rda_server.login_hndlr(create_request(method, url, _data))
            logging.debug(rsp.text + '\n')
            assert rsp.status == 200        

            logging.debug('check db record')
            user_data = yield from cfm_rda_server._db.get_object('users', {'callsign': _data['callsign']},\
                    False)
            logging.debug(user_data)
            logging.debug('\n')
            assert user_data
            assert user_data['email'] == _data['email']
            assert user_data['password'] == _data['password']
            assert user_data['email_confirmed']

            method = 'POST'

            logging.debug('Change password request - invalid recaptcha')
            _data['mode'] = 'passwordRequest'
            _data['callsign'] = 'TEST'
            _data['recaptcha'] ='hf;sadhf;aschn;sadhnac;'
            rsp = yield from cfm_rda_server.login_hndlr(create_request(method, url, _data))
            logging.debug(rsp.text + '\n')
            assert rsp.status == 400        

            logging.debug('Change password request')
            _data['recaptcha'] ='mock_true'
            rsp = yield from cfm_rda_server.login_hndlr(create_request(method, url, _data))
            logging.debug(rsp.text + '\n')
            assert rsp.status == 200        
           

        finally:
            if clean_user:
                logging.debug('cleaning user' + '\n')
                yield from cfm_rda_server._db.param_delete('users', {'callsign': 'R7CL'})

    asyncio.get_event_loop().run_until_complete(do_test())

def test_password_change(cfm_rda_server):
    data = {'password': '22222222', 'mode': 'passwordChange'}

    logging.debug('change password test - obsolete token')
    data['token'] = cfm_rda_server.create_token({'time': time.time() - 60 * 70, 'callsign': 'TEST'})
    rsp = requests.post(API_URI + '/login', data=json.dumps(data))
    logging.debug(rsp.text)
    assert rsp.status_code == 400

    logging.debug('change password test')
    data['token'] = cfm_rda_server.create_token({'time': time.time(), 'callsign': 'TEST'})
    rsp = requests.post(API_URI + '/login', data=json.dumps(data))
    logging.debug(rsp.text)
    assert rsp.status_code == 200

def test_login():
    global token
    logging.debug('login test')
    rsp = requests.post(API_URI + '/login',\
        data=json.dumps({'callsign': 'TEST', 'password': '22222222', 'mode': 'login'}))
    logging.debug(rsp.text)
    assert rsp.status_code == 200
    data = json.loads(rsp.text)
    assert data['email'] == 'alexbzg@gmail.com'
    

