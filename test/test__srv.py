#!/usr/bin/python3
#coding=utf-8
import asyncio
import json
import logging
import time
import base64

import os
from os import path

import pytest
from aiohttp.test_utils import make_mocked_request
import requests

import recaptcha
import send_email
from common import site_conf
from json_utils import load_json

def setup_module():
    global CONF    
    CONF = site_conf()
    global WEB_ADDRESS
    WEB_ADDRESS = CONF.get('web', 'address')
    global API_URI
    API_URI = WEB_ADDRESS + '/aiohttp'
    global TEST_USER 
    TEST_USER = pytest.config.getoption('--test_user')
    global TEST_USER_EMAIL
    TEST_USER_EMAIL = pytest.config.getoption('--test_user_email')
    logging.debug('using test user ' + TEST_USER + ' email ' + TEST_USER_EMAIL)
    global TEST_HUNTER
    TEST_HUNTER = pytest.config.getoption('--test_hunter')
    global user_data
    user_data = None
    global loop
    loop = asyncio.get_event_loop()

@pytest.fixture(autouse=True)
def replace_recaptcha(monkeypatch):

    @asyncio.coroutine
    def mock_recaptcha(val):
        return val == 'mock_true'

    def mock_send_email(**kwargs):
        logging.debug('Send email')
        logging.debug(kwargs)
        return True
        
    monkeypatch.setattr(recaptcha, 'check_recaptcha', mock_recaptcha)
    monkeypatch.setattr(send_email, 'send_email', mock_send_email)


class MockPayload():

    def __init__(self, data):
        self._bytes = json.dumps(data).encode()

    @asyncio.coroutine
    def readany(self):
        rsp = self._bytes
        self._bytes = b''
        return rsp

def create_request(method, url, data=None):
    req = make_mocked_request(method, url)
    if data:
        req._payload = MockPayload(data)
    return req

def test_login_register(cfm_rda_server):

    @asyncio.coroutine
    def do_test(title,data,expect_code):

        logging.debug('Login/register: ' + title)
        rsp = yield from cfm_rda_server.login_hndlr(create_request("POST", "/aiohttp/login", data))
        logging.debug(rsp.text + '\n')
        assert rsp.status == expect_code

    params = \
    (("register wrong user",
    {'callsign': 'RN6BNL',\
    'password': 'rytqcypz',\
    'mode': 'register',\
    'recaptcha': 'mock_true',\
    'email': TEST_USER_EMAIL},
    400),
    ('register invalid user',
    {'password': 'rytqcypz',\
    'mode': 'register',\
    'recaptcha': 'mock_true',\
    'email': TEST_USER_EMAIL},
    400),
    ('register user',
    {'password': 'rytqcypz',\
    'mode': 'register',\
    'callsign': TEST_USER,\
    'recaptcha': 'mock_true',\
    'email': TEST_USER_EMAIL},
    200),
    ('register exisiting user',
    {'password': 'rytqcypz',\
    'mode': 'register',\
    'callsign': TEST_USER,\
    'recaptcha': 'mock_true',\
    'email': TEST_USER_EMAIL},
    400),
    ('change password request; invalid recaptcha',
    {'mode': 'passwordRequest',\
    'callsign': TEST_USER,\
    'recaptcha': 'l;ajjklvjvv'},
    400),
    ('change password request',
    {'mode': 'passwordRequest',\
    'callsign': TEST_USER,\
    'recaptcha': 'mock_true'},
    200))

    for (title, data, expect_code) in params:
        loop.run_until_complete(do_test(title, data, expect_code))
    loop.run_until_complete(check_db(cfm_rda_server,\
            {'email_confirmed': False,\
            'email': TEST_USER_EMAIL,\
            'password': 'rytqcypz'}))

def test_contact_support(cfm_rda_server):

    @asyncio.coroutine
    def do_test(title,data,expect_code):

        logging.debug('Contact support: ' + title)
        rsp = yield from cfm_rda_server.contact_support_hndlr(create_request("POST", "/aiohttp/support", data))
        logging.debug(rsp.text + '\n')
        assert rsp.status == expect_code

    params = (\
        ('not logged user; invalid recaptcha',
        {'email': '18@73.ru', 
        'recaptcha': 'asgds,cblhav./dsjvab.jkasdbckdjas',
        'text':'blah blah blah blah blah blah blah'},
        400),
         ('not logged user',
        {'email': '18@73.ru', 
        'recaptcha': 'mock_true',
        'text':'blah blah blah blah blah blah blah'},
        200),
        ('logged user',
        {'token': cfm_rda_server.create_token({'callsign': TEST_USER}), 
        'text':'blah blah blah blah blah blah blah'},
        200))
    
    for (title, data, expect_code) in params:
        loop.run_until_complete(do_test(title, data, expect_code))


@asyncio.coroutine
def check_db(cfm_rda_server, expect_data):

    global user_data
    logging.debug('check db record')
    user_data = yield from cfm_rda_server._db.get_object('users', \
        {'callsign': TEST_USER}, False)
    logging.debug(user_data)
    logging.debug('\n')
    for field in expect_data:
         assert user_data[field] == expect_data[field]

def test_confirm_email(cfm_rda_server):
    params = (\
        ('token without callsign',
        {'time': time.time()},
        400),
        ('obsolete token',
        {'time': time.time() - 60 * 70, 'callsign': TEST_USER},
        400),
        ('correct',
        {'time': time.time(), 'callsign': TEST_USER},
        200))

    def do_test(title, data, expect_code):
        logging.debug('Confirm email: ' + title)
        rsp = requests.get(API_URI + '/confirm_email?token=' +\
            cfm_rda_server.create_token(data))
        logging.debug(rsp.text)
        assert rsp.status_code == expect_code

    for (title, data, expect_code) in params:
        do_test(title, data, expect_code)

    loop.run_until_complete(check_db(cfm_rda_server,\
            {'email_confirmed': True}))

def test_password_change(cfm_rda_server):

    def do_test(title, data, expect_code):
        logging.debug('change password test: ' + title)
        data['mode'] = 'passwordChange'
        data['token'] = cfm_rda_server.create_token(data['token'])
        rsp = requests.post(API_URI + '/login', data=json.dumps(data))
        logging.debug(rsp.text)
        assert rsp.status_code == expect_code

    params = (\
        ('obsolete token',
        {'token': {'time': time.time() - 60 * 70, 'callsign': TEST_USER},
        'password': '22222222'},
        400),
         ('correct',
        {'token': {'time': time.time(), 'callsign': TEST_USER},
        'password': '22222222'},
        200))

    for (title, data, expect_code) in params:
        do_test(title, data, expect_code)

    loop.run_until_complete(check_db(cfm_rda_server,\
            {'password': '22222222'}))

def login(title, expect_code):
    logging.debug('login test: title')
    rsp = requests.post(API_URI + '/login',\
        data=json.dumps(\
        {'callsign': user_data['callsign'], 
        'password': user_data['password'], 
        'mode': 'login'}))
    logging.debug(rsp.text)
    assert rsp.status_code == expect_code
    if expect_code == 200:
        data = json.loads(rsp.text)
        assert data['token']
        assert data['email'] == user_data['email']
        user_data['token'] = data['token']
   
def test_login():
    login('correct', 200)


def test_ADIF_upload():

    def do_test(title, data, expect_code, files_loaded):
        logging.debug('ADIF upload: ' + title)
        for file in data['files']:
            adif = None
            with open(path.dirname(path.abspath(__file__)) + '/adif/' + file['name'], 'r') as _tf:
                adif = _tf.read()
            file['file'] = ',' + base64.b64encode(adif.encode()).decode()
        rsp = requests.post(API_URI + '/adif', data=json.dumps(data)) 
        logging.debug(rsp.text + '\n')
        assert rsp.status_code == expect_code
        if expect_code == 200:
            r_data = json.loads(rsp.text)            
            logging.debug(r_data)
            assert r_data['filesLoaded'] == files_loaded

    params = (\
        ('station callsign specified & additional callsigns',
        {'token': user_data['token'],
        'stationCallsign': 'ACTIV0TEST',
        'stationCallsignFieldEnable': False,
        'rdaFieldEnable': False,
        'skipRankings': 1,
        'additionalActivators': 'ACTIVE1TEST, ACTIVE2TEST ACTIVE3TEST',
        'files': [{'name': '0.adi', 'rda': 'HA-01'}]},
        200, 1),
        ('rda field enabled but not specified',
        {'token': user_data['token'],
        'stationCallsign': 'ACTIV0TEST',
        'stationCallsignFieldEnable': False,
        'rdaFieldEnable': True,
        'skipRankings': 1,
        'additionalActivators': 'ACTIVE1TEST, ACTIVE2TEST ACTIVE3TEST',
        'files': [{'name': '0.adi'}]},
        400, 0),
        ('missing rda field in qso',
        {'token': user_data['token'],
        'stationCallsign': 'ACTIV0TEST',
        'stationCallsignFieldEnable': False,
        'rdaFieldEnable': True,
        'rdaField': 'STATE',
        'skipRankings': 1,
        'additionalActivators': 'ACTIVE1TEST, ACTIVE2TEST ACTIVE3TEST',
        'files': [{'name': '1.adi'}]},
        200, 0),
        ('valid rda field in qso',
        {'token': user_data['token'],
        'stationCallsign': 'ACTIV0TEST',
        'stationCallsignFieldEnable': False,
        'rdaFieldEnable': True,
        'rdaField': 'STATE',
        'skipRankings': 1,
        'additionalActivators': 'ACTIVE1TEST, ACTIVE2TEST ACTIVE3TEST',
        'files': [{'name': '2.adi'}]},
        200, 1),
        ('station callsign from field',
        {'token': user_data['token'],
        'stationCallsignField': 'STATION_CALLSIGN',
        'skipRankings': 1,
        'rdaFieldEnable': False,
        'stationCallsignFieldEnable': True,
        'files': [{'name': '0_1.adi', 'rda': 'HA-02'}]},
        200, 1),
        ('duplicate file',
        {'token': user_data['token'],
        'stationCallsignField': 'STATION_CALLSIGN',
        'skipRankings': 1,
        'rdaFieldEnable': False,
        'stationCallsignFieldEnable': True,
        'files': [{'name': '0.adi', 'rda': 'HA-02'}]},
        200, 0),
        ('station callsign from invalid field',
        {'token': user_data['token'],
        'stationCallsignField': 'STATION_CALLSIGN_',
        'rdaFieldEnable': False,
        'stationCallsignFieldEnable': True,
        'files': [{'name': '0.adi', 'rda': 'HA-01'}]},
        200, 0),
        ('multiple station callsigns',
        {'token': user_data['token'],
        'stationCallsignField': 'STATION_CALLSIGN',
        'rdaFieldEnable': False,
        'stationCallsignFieldEnable': True,
        'files': [{'name': '1.adi', 'rda': 'HA-01'}]},
        200, 0))

    for (title, data, expect_code, files_loaded) in params:
        do_test(title, data, expect_code, files_loaded)

    check_hunter_data(CONF, TEST_HUNTER)
    check_hunter_data(CONF, 'ACTIVE1TEST', 'activator')

def test_user_uploads(cfm_rda_server):
    logging.debug('User uploads - regular user')
    rsp = requests.post(API_URI + '/user_uploads',\
        data=json.dumps({'token': user_data['token']}))
    assert rsp.status_code == 200
    data = json.loads(rsp.text)            
    logging.debug(data)
    assert data
    assert len(data) == 3

    logging.debug('User uploads - admin')
    rsp = requests.post(API_URI + '/user_uploads',\
        data=json.dumps({'token':\
            cfm_rda_server.create_token({'callsign': 'TEST'})}))
    assert rsp.status_code == 200
    data = json.loads(rsp.text)            
    logging.debug(data)
    assert data
    assert len(data) > 3


def check_hunter_data(conf, callsign, role='hunter', rda='HA-01'):
    rsp = requests.get(API_URI + '/hunter/' + callsign) 
    assert rsp.status_code == 200
    data = json.loads(rsp.text)            
    logging.debug(data)
    assert data
    assert 'qso' in data    
    assert rda in data['qso']
    assert role in data['qso'][rda]
    assert data['qso'][rda][role]

