#!/usr/bin/python3
#coding=utf-8

import logging
import sys
import pytest
import asyncio
import os 

sys.path.append('test')
sys.path.append('cfmrda')

from srv import CfmRdaServer
from common import site_conf

TEST_USER = 'RN6BN'
TEST_EMAIL = 'rn6bn@mail.ru'
TEST_HUNTER = "HUNTER0TEST"

def pytest_addoption(parser):
    parser.addoption("--test_user", action="store", default=TEST_USER,
        help="uploader callsign")
    parser.addoption("--test_user_email", action="store", default=TEST_EMAIL,
        help="uploader email")
    parser.addoption("--test_hunter", action="store", default=TEST_HUNTER,
        help="hunter callsign")


@pytest.fixture(scope="session", autouse=True)
def cfm_rda_server():

    loop = asyncio.get_event_loop()
    srv = CfmRdaServer(loop) 

    logging.basicConfig( level = logging.DEBUG,
            format='%(asctime)s %(message)s', 
            datefmt='%Y-%m-%d %H:%M:%S' )
    logging.info( 'starting tests' )

    global TEST_USER 
    TEST_USER = pytest.config.getoption('--test_user')
    global TEST_USER_EMAIL
    TEST_USER_EMAIL = pytest.config.getoption('--test_user_email')
    global TEST_HUNTER
    TEST_USER = pytest.config.getoption('--test_user')
    hunter_file = site_conf().get('web', 'root') +\
            '/json/hunters/' + TEST_HUNTER + '.json'

    @asyncio.coroutine
    def teardown():
        
        if os.path.isfile(hunter_file):
            os.remove(hunter_file)
        yield from asyncio.sleep(0.1)
        logging.debug('cleaning user ' + TEST_USER)
        yield from srv._db.execute( 
                """delete from qso e 
                    where callsign = 'TE1ST' and station_callsign = 'R7CL/M'""")
        yield from srv._db.execute( 
                """delete from qso 
                    where exists 
                        (select user_cs from uploads
                        where uploads.id = qso.upload_id and 
                            user_cs = %(callsign)s)""", 
                        {'callsign': TEST_USER})
        yield from srv._db.execute( 
                """delete from activators 
                    where exists 
                        (select user_cs from uploads
                        where uploads.id = activators.upload_id and 
                            user_cs = %(callsign)s)""", 
                        {'callsign': TEST_USER})
        yield from srv._db.param_delete('uploads', {'user_cs': TEST_USER})
        yield from srv._db.param_delete('users', {'callsign': TEST_USER})
 
    loop.run_until_complete(teardown())
    yield srv
    loop.run_until_complete(teardown())


