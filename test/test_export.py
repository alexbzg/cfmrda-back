#!/usr/bin/python3
#coding=utf-8

import asyncio

import pytest

from export import export_rankings, export_hunters
from common import site_conf

conf = site_conf()
loop = asyncio.get_event_loop()

def test_export_rankings():

    loop.run_until_complete(export_rankings(conf))


