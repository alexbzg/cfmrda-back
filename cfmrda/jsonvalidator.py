#!/usr/bin/python3
#coding=utf-8

from jsonschema import validate

from common import site_conf, load_json

class JSONvalidator:

    def __init__(self):
        conf = site_conf()
        self._schemas = load_json(conf.get('web', 'root') + '/json/schemas.json')

    def validate(self, schema, data):
        return validate(data, self._schemas[schema])

