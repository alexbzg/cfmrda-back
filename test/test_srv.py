#!/usr/bin/python3
#coding=utf-8
import asyncio
import json
import logging

import pytest
from aiohttp.test_utils import make_mocked_request

from srv import CfmRdaServer
import recaptcha

@pytest.fixture(autouse=True)
def replace_recaptcha(monkeypatch):

    @asyncio.coroutine
    def mock_recaptcha(val):
        return val == 'mock_true'
        
    monkeypatch.setattr(recaptcha, 'check_recaptcha', mock_recaptcha)

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

    _data = {'callsign': 'RN6BNN',\
            'password': 'rytqcypz',\
            'register': True,\
            'recaptcha': 'mock_true',\
            'email': 'rn6bn@mail.ru'}

    def create_request(data):
        req = make_mocked_request( 'POST', '/aiohttp/login' )
        req._payload = MockPayload(data)
        req._client_max_size = 0
        return req

    @asyncio.coroutine
    def do_test():
        yield from asyncio.sleep(0.1)

        logging.debug('Creating wrong user')
        rsp = yield from cfm_rda_server.login_hndlr(create_request(_data))
        logging.debug(rsp.text + '\n')
        assert rsp.status == 400

        logging.debug('Creating wrong user with wrong email')
        _data['callsign'] = 'RN6BN'
        _data['email'] = '_rn6bn@mail.ru'
        rsp = yield from cfm_rda_server.login_hndlr(create_request(_data))
        logging.debug(rsp.text + '\n')
        assert rsp.status == 400

        logging.debug('Creating user')
        _data['email'] = 'rn6bn@mail.ru'
        rsp = yield from cfm_rda_server.login_hndlr(create_request(_data))
        logging.debug(rsp.text + '\n')
        assert rsp.status == 200

        logging.debug('Creating dublicate user')
        rsp = yield from cfm_rda_server.login_hndlr(create_request(_data))
        logging.debug(rsp.text + '\n')
        assert rsp.status == 400        

        logging.debug('cleaning user' + '\n')
        yield from cfm_rda_server._db.param_delete('users', {'callsign': 'RN6BN'})

    asyncio.get_event_loop().run_until_complete(do_test())

