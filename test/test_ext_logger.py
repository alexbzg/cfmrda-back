#!/usr/bin/python3
#coding=utf-8
import logging
from os import path
import pytest

from ext_logger import ExtLogger
from json_utils import load_json

LOTW_LOGIN = load_json(path.dirname(path.abspath(__file__)) + '/lotw_login.json')

def test_lotw_login():
    lotw = ExtLogger('LOTW')
    logging.warning('test LOTW login')
    login_ssn = lotw.login(LOTW_LOGIN)
    assert login_ssn
    lotw = ExtLogger('LOTW')
    bad_login = {}
    bad_login.update(LOTW_LOGIN)
    bad_login['password'] += '_'
    bad_login_ssn = lotw.login(bad_login)

def test_lotw_dowload():
    lotw = ExtLogger('LOTW')
    logging.warning('test LOTW download')
    adif = lotw.download(LOTW_LOGIN, date_from='2019-06-13')
    assert adif
    logging.warning(adif)

