#!/usr/bin/python3
#coding=utf-8

import asyncio

import pytest

from export import export_rankings, export_hunters
from common import site_conf
from json_utils import load_json

from test__srv import check_hunter_file

conf = site_conf()
WEB_ROOT = conf.get('web', 'root')
loop = asyncio.get_event_loop()

def test_export_rankings():

    loop.run_until_complete(export_rankings(conf))
    
    rankings = load_json(WEB_ROOT + '/json/rankings.json')
    act = rankings['activators']['bands']['14'][0]
    assert act['rank'] == 1
    assert act['callsign']
    act = rankings['activators']['bandsSum'][0]
    assert act['rank'] == 1
    assert act['callsign']
    act = rankings['activators']['total'][0]
    assert act['rank'] == 1
    assert act['callsign']
  
    hunt = rankings['hunters']['bands']['14'][0]
    assert hunt['rank'] == 1
    assert hunt['callsign']
    hunt = rankings['hunters']['bandsSum'][0]
    assert hunt['rank'] == 1
    assert hunt['callsign']
    hunt = rankings['hunters']['total'][0]
    assert hunt['rank'] == 1
    assert hunt['callsign']

def test_export_hunters():
    loop.run_until_complete(export_hunters(conf))
    check_hunter_file(conf)

