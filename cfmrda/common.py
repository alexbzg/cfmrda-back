#!/usr/bin/python3
#coding=utf-8


import configparser
import decimal
import json

import logging
import logging.handlers

from os import path
from datetime import datetime, date

APP_ROOT = path.dirname(path.abspath(__file__))

def site_conf():
    conf = configparser.ConfigParser()
    conf.optionxform = str
    conf.read(APP_ROOT + '/site.conf')
    return conf

def json_encode_extra(obj):
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, date):
        return obj.isoformat()
    raise TypeError(repr(obj) + " is not JSON serializable")

def load_json(path_json):
    if not path.isfile(path_json):
        logging.exception(path_json + " not found")
        return False
    try:
        data = json.load(open(path_json))
        return data
    except Exception:
        logging.exception("Error loading " + path_json)
        return False

def start_logging(log_type, level=logging.DEBUG):
    conf = site_conf()
    fp_log = conf.get('logs', log_type)
    logger = logging.getLogger('')
    logger.setLevel(level)
    handler = logging.handlers.WatchedFileHandler(fp_log)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(\
        '%(asctime)s %(name)-12s %(levelname)-8s %(message)s'))
    logger.addHandler(handler)


