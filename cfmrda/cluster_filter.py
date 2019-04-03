#!/usr/bin/python3
#coding=utf-8
"""functions for exporting stats data from db to frontend json files"""
import asyncio
import logging

from common import site_conf, start_logging
from db import DBConn
from json_utils import load_json, save_json

@asyncio.coroutine
def perform(conf):
    """cluster filtering"""
    logging.debug('cluster filtering')
    list_length = conf.getint('cluster', 'list_length')

    _db = DBConn(conf.items('cluster_db'))
    yield from _db.connect()

    _dx = load_json(conf.get('files', 'cluster'))
    if not _dx:
        logging.error('Cluster data not found')
        return

    dxped = yield from _db.execute("""
                select json_object_agg(callsign, 
                    json_build_object('desc', descr, 'link', link)) as data
                from dxpedition 
                where (dt_begin < now() or dt_begin is null) 
                    and (dt_end > now() or dt_end is null)""", False)
    rda_dx_fname = conf.get('web', 'root') + '/json/dx.json'
    rda_dx = load_json(rda_dx_fname)
    prev = None
    if rda_dx:
        prev = rda_dx[0]
    else:
        rda_dx = []
    idx = 0
    for item in reversed(_dx):
        if prev and item['ts'] < prev['ts']:
            break
        if 'RDA' in item['awards'] or item['cs'] in dxped:
            if item['cs'] in dxped:
                item['dxped'] = dxped[item['cs']]
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

