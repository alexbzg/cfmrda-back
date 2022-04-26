#!/usr/bin/python3
#coding=utf-8
"""functions for exporting stats data from db to frontend json files"""
import asyncio
import logging

from common import site_conf, start_logging
from db import DBConn
from json_utils import load_json, save_json

async def perform(conf):
    """cluster filtering"""
    logging.debug('cluster filtering')
    list_length = conf.getint('cluster', 'list_length')

    _db = DBConn(dict(conf.items('db')))
    await _db.connect()

    _dx = load_json(conf.get('files', 'cluster'))
    if not _dx:
        logging.error('Cluster data not found')
        return

    idx = 0
    for item in reversed(_dx):
        if prev and item['ts'] <= prev['ts']:
            break
        if 'RDA' in item['awards']:
            if item['mode'] == 'DATA':
                item['mode'] = 'DIGI'
            rda_dx.insert(idx, item)
            idx += 1
    if len(rda_dx) > list_length:
        rda_dx = rda_dx[:list_length]
    save_json(rda_dx, rda_dx_fname)

def main():
    """call from shell"""
    conf = site_conf()
    start_logging('cluster')

    asyncio.get_event_loop().run_until_complete(perform(conf))

if __name__ == "__main__":
    main()

