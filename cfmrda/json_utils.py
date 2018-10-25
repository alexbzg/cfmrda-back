#!/usr/bin/python3
#coding=utf-8

import json
import logging
import os
import decimal

from datetime import datetime, date

import jsonschema

def json_encode_extra(obj):
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
        return False
    try:
        data = json.load(open(path_json))
        return data
    except Exception:
        logging.exception("Error loading " + path_json)
        return False

def save_json(data, path_json):
    """saves data to json file"""
    with open(path_json, 'w') as file:
        json.dump(data, file, ensure_ascii=False)

class JSONvalidator:

    def __init__(self, schemas):
        self._schemas = schemas

    def validate(self, schema, data):
        try:
            jsonschema.validate(data, self._schemas[schema])
            return True
        except jsonschema.exceptions.ValidationError:
            logging.error('Error validating json data. Schema: ' + schema)
            logging.error(data)
            return False
