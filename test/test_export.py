#!/usr/bin/python3
#coding=utf-8

import asyncio

import pytest

from export import export_rankings
from common import site_conf
from json_utils import load_json

conf = site_conf()
WEB_ROOT = conf.get('web', 'root')
loop = asyncio.get_event_loop()

def test_export_rankings():

    loop.run_until_complete(export_rankings(conf))
    
    rankings = load_json(WEB_ROOT + '/json/rankings.json')
    act = rankings['activator']['total']['total'][0]
    assert act['rank'] == 1
    assert act['callsign']
  
    hunt = rankings['hunter']['total']['total'][0]
    assert hunt['rank'] == 1
    assert hunt['callsign']


