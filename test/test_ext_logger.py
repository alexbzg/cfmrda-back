#!/usr/bin/python3
#coding=utf-8
import logging
from os import path
import pytest

from ext_logger import ExtLogger, ExtLoggerException
from json_utils import load_json

LOGINS = load_json(path.dirname(path.abspath(__file__)) + '/loggers_logins.json')

def test_login():
    for logger_type, login in LOGINS.items():
        logger = ExtLogger(logger_type)
        logging.warning('test ' + logger_type + ' login')
        login_ssn = logger.login(login)
        assert login_ssn
        logging.warning('OK')
        logger = ExtLogger(logger_type)
        logging.warning('test ' + logger_type + ' bad login')
        bad_login = {field: value + '_' for field, value in login.items()}
        try:
            bad_login_ssn = logger.login(bad_login)
        except ExtLoggerException as e:
            assert str(e) == 'Login failed.'
            logging.warning('OK')

def test_lotw_load():
    lotw = ExtLogger('LoTW')
#    logging.warning('test LOTW download')
    adif = lotw.load(LOGINS['LoTW'], date_from='2019-06-13')
    assert adif
    logging.warning(adif)

def test_hamlog_load():
    lotw = ExtLogger('HamLOG')
#    logging.warning('test LOTW download')
    adif = lotw.load(LOGINS['HamLOG'])
    assert adif
    assert len(adif) == 2
    logging.warning(adif[0][:500])
    logging.warning('--------------------------------')
    logging.warning(adif[1][:500])

