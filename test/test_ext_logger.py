#!/usr/bin/python3
#coding=utf-8
import logging
from os import path
import pytest
from datetime import date

from ext_logger import ExtLogger, ExtLoggerException
from json_utils import load_json

LOGINS = load_json(path.dirname(path.abspath(__file__)) + '/loggers_logins.json')

def test_login():
    for logger_type, login in LOGINS.items():
        logger = ExtLogger(logger_type)
        logging.info('test ' + logger_type + ' login')
        login_ssn = logger.login(login)
        assert login_ssn
        logging.info('OK')
        logger = ExtLogger(logger_type)
        logging.info('test ' + logger_type + ' bad login')
        bad_login = {field: value + '_' for field, value in login.items()}
        try:
            bad_login_ssn = logger.login(bad_login)
        except ExtLoggerException as e:
            assert str(e) == 'Login failed.'
            logging.info('OK')

def test_load():
    kwparams = {'LoTW': {'date_from': '2019-07-13'},\
            'eQSL': {'date_from': date(2019, 1, 1)}}
                
    for logger_type, login in LOGINS.items():
        logger = ExtLogger(logger_type)
        logging.info('test ' + logger_type + ' download')

        kwp = kwparams[logger_type] if logger_type in kwparams else {}

        adifs = logger.load(login, **kwp)
        assert adifs
        logging.info(str(len(adifs)) + ' adif files were downloaded')
        for adif in adifs:
            lines = adif.split('\n')
            logging.info('-------------------------------------------------')
            for line in lines[:10]:
                logging.info(line)

