#!/usr/bin/python3
#coding=utf-8

import asyncio

import pytest

from export import export_rankings, export_recent_uploads, export_msc
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

def test_export_recent_uploads():

    loop.run_until_complete(export_recent_uploads(conf))
    
    rec_upl = load_json(WEB_ROOT + '/json/recent_uploads.json')
    assert rec_upl
    assert rec_upl[0]['tstamp']
    assert rec_upl[0]['rda']

def test_export_msc():

    loop.run_until_complete(export_msc(conf))
    
    data = load_json(WEB_ROOT + '/json/msc.json')
    assert data['qsoCount']

