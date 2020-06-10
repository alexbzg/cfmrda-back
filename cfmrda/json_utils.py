#!/usr/bin/python3
#coding=utf-8

import json
import logging
import os
import decimal

from datetime import datetime, date

import jsonschema

def json_encode_extra(obj):
    """encoder for json.dump(s) with extra types support"""
#    return str(type(obj))
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, date):
        return obj.isoformat()
    raise TypeError(repr(obj) + " is not JSON serializable")

def load_json(path_json):
    """loads json data from path, returns data or None when fails"""
    if not os.path.isfile(path_json):
        logging.exception(path_json + " not found")
        return None
    try:
        data = json.load(open(path_json))
        return data
    except Exception:
        logging.exception("Error loading " + path_json)
        return None

def save_json(data, path_json):
    """saves data to json file"""
    with open(path_json, 'w') as file:
        json.dump(data, file, ensure_ascii=False)

def deep_copy_trunc(src, size_limit=1024):
    rslt = None
    if isinstance(src, dict):
        rslt = {}
        for key, val in src.items():
            rslt[key] = deep_copy_trunc(val, size_limit)
    elif isinstance(src, list):
        rslt = []
        for item in src:
            rslt.append(deep_copy_trunc(item, size_limit))
    elif isinstance(src, str):
        rslt = src if size_limit > 0 and len(src) < size_limit\
                else src[:size_limit] + '_etc'
    else:
        rslt = src
    return rslt
        
class JSONvalidator:

    def __init__(self, schemas):
        self._schemas = schemas

    def validate(self, schema, data):
        try:
            jsonschema.validate(deep_copy_trunc(data), self._schemas[schema])
            return True
        except jsonschema.exceptions.ValidationError as exc:
            logging.error('Error validating json data. Schema: ' + schema)
            logging.exception(exc)
            return False
