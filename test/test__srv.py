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
import secret
from common import site_conf
from json_utils import load_json

def setup_module():
    global CONF    
    CONF = site_conf()
    global SECRET
    SECRET = secret.get_secret(CONF.get('files', 'secret'))
    global WEB_ADDRESS
    WEB_ADDRESS = CONF.get('web', 'address')
    global WEB_ROOT
    WEB_ROOT = CONF.get('web', 'root')
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

def create_token(data):
    return secret.create_token(SECRET, data)

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

def login(login_data):
    login_data['mode'] = 'login'
    rsp = requests.post(API_URI + '/login', data=json.dumps(login_data))
    logging.debug(rsp.text)
    assert rsp.status_code == 200
    data = json.loads(rsp.text)
    assert data['token']
    return data


def test_login():
    logging.debug('login test')
    login_data = {'callsign': 'TE1ST', 
        'password': '11111111'}

    data = login(login_data)
    assert data['oldCallsigns']['confirmed']
    login_data['callsign'] = 'TE1STOLD'
    data = login(login_data())
    assert data['newCallsign']
   
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
    user_data['uploads'] = data

    logging.debug('User uploads - admin')
    rsp = requests.post(API_URI + '/user_uploads',\
        data=json.dumps({'token':\
            cfm_rda_server.create_token({'callsign': 'TE1ST'})}))
    assert rsp.status_code == 200
    data = json.loads(rsp.text)            
    logging.debug(data)
    assert data
    assert len(data) > 3

def test_manage_uploads(cfm_rda_server):
    logging.debug('Delete file - user')
    rsp = requests.post(API_URI + '/manage_uploads',\
        data=json.dumps({\
            'token': user_data['token'],\
            'delete': 1,\
            'skipRankings': 1,\
            'id': user_data['uploads'][0]['id']}))
    assert rsp.status_code == 200

    logging.debug('Delete file - wrong user')
    rsp = requests.post(API_URI + '/manage_uploads',\
        data=json.dumps({\
            'token': cfm_rda_server.create_token({'callsign': 'RD1A'}),\
            'delete': 1,\
            'skipRankings': 1,\
            'id': user_data['uploads'][1]['id']}))
    assert rsp.status_code == 400
   
    logging.debug('Delete file - admin')
    rsp = requests.post(API_URI + '/manage_uploads',\
        data=json.dumps({\
            'token': cfm_rda_server.create_token({'callsign': 'TE1ST'}),\
            'delete': 1,\
            'skipRankings': 1,\
            'id': user_data['uploads'][1]['id']}))
    assert rsp.status_code == 200

    logging.debug('Disable file - admin')
    rsp = requests.post(API_URI + '/manage_uploads',\
        data=json.dumps({\
            'token': cfm_rda_server.create_token({'callsign': 'TE1ST'}),\
            'enabled': False,\
            'skipRankings': 1,\
            'id': user_data['uploads'][1]['id']}))
    assert rsp.status_code == 200

    logging.debug('Delete file - admin')
    rsp = requests.post(API_URI + '/manage_uploads',\
        data=json.dumps({\
            'token': cfm_rda_server.create_token({'callsign': 'TE1ST'}),\
            'enabled': True,\
            'skipRankings': 1,\
            'id': user_data['uploads'][1]['id']}))
    assert rsp.status_code == 200

def test_cfm_request_qso():
    logging.debug('Cfm request qso')
    rsp = requests.post(API_URI + '/cfm_request_qso',\
        data=json.dumps({
            'token': create_token({'callsign': 'TE1ST'}),
            'qso': [{\
                'callsign': 'TE1ST',\
                'stationCallsign': 'R7CL/M',\
                'correspondent': 'R7CL',
                'email': 'welcome@masterslav.ru',
                'rda': 'HA-01',\
                'band': '10', 
                'mode': 'CW', 
                'date': '20180725',
                'time': '1217', 
                'recRST': '-40', 
                'sentRST': '+20'
                }]
            }))    
    logging.debug(rsp.text)
    assert rsp.status_code == 200

    logging.debug('Cfm request qso - bad recaptcha')
    rsp = requests.post(API_URI + '/cfm_request_qso',\
        data=json.dumps({
            'email': '18@63.ru',
            'recaptcha': 'd,gafbdsjagf,la',
            'qso': [{\
                'callsign': 'TE1ST',\
                'stationCallsign': 'R7CL/M',\
                'correspondent': 'R7CL',
                'email': 'welcome@masterslav.ru',
                'rda': 'HA-01',\
                'band': '10', 
                'mode': 'CW', 
                'date': '20180725',
                'time': '1217', 
                'recRST': '-40', 
                'sentRST': '+20'
                }]
            }))    
    logging.debug(rsp.text)
    assert rsp.status_code == 400

def test_cfm_qso():
    logging.debug('Cfm qso list')
    rsp = requests.post(API_URI + '/cfm_qso',\
        data=json.dumps({
            'token': create_token({'callsign': 'R7CL'})
                }))
    logging.debug(rsp.text)
    assert rsp.status_code == 200
    data = json.loads(rsp.text)

    logging.debug('Cfm qso list -- unregistered user')
    rsp = requests.post(API_URI + '/cfm_qso',\
        data=json.dumps({
            'token': create_token({'callsign': 'RN6BN'})
                }))
    logging.debug(rsp.text)
    assert rsp.status_code == 200
    data = json.loads(rsp.text)

    logging.debug('Cfm qso changes')
    rsp = requests.post(API_URI + '/cfm_qso',\
        data=json.dumps({
            'token': create_token({'callsign': 'R7CL'}),
            'qso': {'cfm':[data[0]['id']]}
                }))
    logging.debug(rsp.text)
    assert rsp.status_code == 200

def test_chat():

    chat_path = WEB_ROOT + '/json/chat.json'
    active_users_path = WEB_ROOT + '/json/active_users.json'

    logging.debug('chat -- post from logged user')
    data = {\
        'token': create_token({'callsign': 'R7CL'}),\
        'message': 'blah 0',\
        'name': 'Name 0'}
    rsp = requests.post(API_URI + '/chat',\
        data=json.dumps(data))
    logging.debug(rsp.text)
    assert rsp.status_code == 200
    chat = load_json(chat_path)
    assert chat
    assert chat[0]
    assert chat[0]['callsign'] == 'R7CL'
    assert chat[0]['admin']
    assert chat[0]['text'] == data['message']
    assert chat[0]['name'] == data['name']
    assert chat[0]['ts']
    assert chat[0]['date']
    assert chat[0]['time']
    au = load_json(active_users_path)
    assert au
    assert au['R7CL']
    assert int(au['R7CL']['ts']) - int(chat[0]['ts']) < 2

    logging.debug('chat -- post from not logged user')
    data = {\
        'callsign': 'B1AH',\
        'message': 'blah 0',\
        'name': 'Name 1'}
    rsp = requests.post(API_URI + '/chat',\
        data=json.dumps(data))
    logging.debug(rsp.text)
    assert rsp.status_code == 200
    chat = load_json(chat_path)
    assert chat
    assert chat[0]
    assert chat[0]['callsign'] == data['callsign']
    assert not chat[0]['admin']
    assert chat[0]['name'] == data['name']
    assert chat[0]['text'] == data['message']
    assert chat[0]['ts']
    assert chat[0]['date']
    assert chat[0]['time']
    au = load_json(active_users_path)
    assert au
    assert au[data['callsign']]
    assert int(au[data['callsign']]['ts']) - int(chat[0]['ts']) < 2

    del_ts = chat[0]['ts']
    logging.debug('chat -- admin deletes post')
    data = {\
        'token': create_token({'callsign': 'R7CL'}),\
        'delete': del_ts,}
    rsp = requests.post(API_URI + '/chat',\
        data=json.dumps(data))
    logging.debug(rsp.text)
    assert rsp.status_code == 200
    chat = load_json(chat_path)
    assert chat
    assert chat[0]['ts'] != del_ts

    logging.debug('chat -- user leaves chat')
    data = {\
        'callsign': 'B1AH',\
        'exit': True}
    rsp = requests.post(API_URI + '/chat',\
        data=json.dumps(data))
    logging.debug(rsp.text)
    assert rsp.status_code == 200
    au = load_json(active_users_path)
    assert au
    assert data['callsign'] not in au
    logging.debug('chat -- user status update')
    data = {\
        'callsign': 'B1AH',\
        'typing': True}
    rsp = requests.post(API_URI + '/chat',\
        data=json.dumps(data))
    logging.debug(rsp.text)
    assert rsp.status_code == 200
    au = load_json(active_users_path)
    assert au
    assert au[data['callsign']]['typing']

def test_cfm_qsl_qso():
    qsl_image = None
    with open(path.dirname(path.abspath(__file__)) + '/qsl.jpg', 'rb') as _tf:
        qsl_image = _tf.read()
        qsl_image = ',' + base64.b64encode(qsl_image).decode()
    qso = {\
        'callsign': 'TE1ST',\
        'stationCallsign': 'R7CL/M',\
        'rda': 'HA-01',\
        'band': '10',\
        'mode': 'CW',\
        'date': '20180725',\
        'time': '1218',\
        'image': {\
            'name': 'qsl.jpg',\
            'file': qsl_image
            }
        }
    token = create_token({'callsign': 'TE1ST'})
    qsl_path = CONF.get('web', 'root') + '/qsl_images/'

    def cfm_qsl_qso(data):
        data['token'] = token
        return requests.post(API_URI + '/cfm_qsl_qso', data=json.dumps(data))

    def new_qsl():
        rsp = cfm_qsl_qso({'qso': qso})    
        logging.debug(rsp.text)
        assert rsp.status_code == 200

    data = None
    def qsl_file_path(index): 
        return qsl_path + str(data[index]['id']) + '_' + data[index]['image']

    logging.debug('Cfm qsl qso -- new')
    new_qsl()
    qso['time'] = '1219'
    new_qsl()
    qso['time'] = '1220'
    new_qsl()
    
    logging.debug('Cfm qsl qso -- list')
    rsp = cfm_qsl_qso({})
    logging.debug(rsp.text)
    assert rsp.status_code == 200
    data = json.loads(rsp.text)
    assert data
    assert data[0]
    assert data[0]['callsign'] == qso['callsign']
    assert data[0]['image'] == qso['image']['name']
    assert path.isfile(qsl_file_path(0))


    def qsl_admin(data):
        return requests.post(API_URI + '/qsl_admin', data=json.dumps(data))

    logging.debug('qsl admin -- list')
    rsp = qsl_admin({'token': token})
    logging.debug(rsp.text)
    assert rsp.status_code == 200
    data = json.loads(rsp.text)
    assert data
    assert data[0]
    assert data[0]['callsign'] == qso['callsign']
    assert data[0]['image'] == qso['image']['name']

    logging.debug('qsl admin -- not authorized')
    rsp = qsl_admin({'token':  create_token({'callsign': 'TE1STA'})})
    logging.debug(rsp.text)
    assert rsp.status_code == 400

    logging.debug('qsl admin -- manage')
    rsp = qsl_admin({'token': token,\
            'qsl': [{'id': data[0]['id'], 'state': True, 'comment': None},\
            {'id': data[1]['id'], 'state': False, 'comment': 'blah blah'}]})
    assert rsp.status_code == 200
    assert not path.isfile(qsl_file_path(0))
    assert not path.isfile(qsl_file_path(1))

    logging.debug('Cfm qsl qso -- delete')
    rsp = cfm_qsl_qso({'delete': data[2]['id']})
    logging.debug(rsp.text)
    assert rsp.status_code == 200
    assert not path.isfile(qsl_file_path(2))

def test_old_callsigns():
    callsign = 'TE1ST'
    old_callsigns = ['TE1STOLD', 'TE1STOLDOLD']

    def request():
        return requests.post(API_URI + '/old_callsigns',\
            data=json.dumps({'token': create_token({'callsign': callsign}),\
                'callsigns': old_callsigns}))

    def check():
        login_data = {'callsign': callsign, 'password': '11111111'}
        user_data = login(login_data)
        assert not set(old_callsigns).difference(\
            set(user_data['oldCallsigns']['all']))
        
    logging.debug('Old callsigns -- add')
    rsp = request()
    logging.debug(rsp.text)
    assert rsp.status_code == 200
    check()

    logging.debug('Old callsigns -- delete')
    old_callsigns = ['TE1STOLD']
    rsp = request()
    logging.debug(rsp.text)
    assert rsp.status_code == 200
    check()

    logging.debug('Old callsigns -- login callsign is old too')
    callsign = 'TE1STOLD'
    old_callsigns = ['TE1STOLDOLD']
    rsp = request()
    logging.debug(rsp.text)
    assert rsp.status_code == 200
    old_callsigns = []
    check()

def test_old_callsigns_admin():
    admin = 'TE1ST'
    callsign = 'R7AB'
    old_callsigns = ['RN6BN', 'RN6BNOLD']

    def request(cfm):
        data = {'token': create_token({'callsign': admin})}
        if cfm:
            data['confirm'] = {'new': callsign,
                'old': old_callsigns}
        return requests.post(API_URI + '/old_callsigns_admin',\
            data=json.dumps(data))

    def check():
        data = json.loads(request(False).text)
        logging.debug(data)
        user_data = [x for x in data if x['new'] == callsign][0]
        assert user_data['confirmed']
        user_callsigns = set([x['callsign'] for x in user_data['old']])
        assert not set(old_callsigns).difference(user_callsigns)
        
    logging.debug('Old callsigns -- admin')
    rsp = request(False)
    logging.debug(rsp.text)
    assert rsp.status_code == 200

    logging.debug('Old callsigns -- admin edit')
    rsp = request(True)
    logging.debug(rsp.text)
    assert rsp.status_code == 200
    check()

    old_callsigns = ['RN6BN', 'R6AUV']
    rsp = request(True)

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

