#!/usr/bin/python3
#coding=utf-8

from common import site_conf
from secret import get_secret, create_token

conf = site_conf()
secret = get_secret(conf.get('files', 'secret'))

print(create_token(secret, {'callsign': 'RN6BN'}))

