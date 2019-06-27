#!/usr/bin/python3
#coding=utf-8
import logging
from os import path
import pytest

from ext_logger import ExtLogger, ExtLoggerException
from json_utils import load_json

LOGINS = load_json(path.dirname(path.abspath(__file__)) + '/loggers_logins.json')

def test_lotw_login():
    lotw = ExtLogger('LoTW')
    logging.warning('test LOTW login')
    login_ssn = lotw.login(LOGINS['LoTW'])
    assert login_ssn
    logging.warning('test LOTW bad login')
    lotw = ExtLogger('LoTW')
    bad_login = {}
    bad_login.update(LOGINS['LoTW'])
    bad_login['password'] += '_'
    try:
        bad_login_ssn = lotw.login(bad_login)
    except ExtLoggerException as e:
        assert str(e) == 'Login failed.'

def test_hamlog_login():
    lotw = ExtLogger('HamLOG')
    logging.warning('test HamLOG login')
    login_ssn = lotw.login(LOGINS['HamLOG'])
    assert login_ssn
    logging.warning('test HamLOG bad login')
    lotw = ExtLogger('HamLOG')
    bad_login = {}
    bad_login.update(LOGINS['HamLOG'])
    bad_login['password'] += '_'
    try:
        bad_login_ssn = lotw.login(bad_login)
    except ExtLoggerException as e:
        assert str(e) == 'Login failed.'


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

