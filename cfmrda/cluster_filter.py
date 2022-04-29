#!/usr/bin/python3
#coding=utf-8
"""functions for exporting stats data from db to frontend json files"""
import asyncio
import logging

from common import site_conf, start_logging
from db import DBConn, exec_cur
from json_utils import load_json, save_json
from dx_spot import DX

async def perform(conf):
    """cluster filtering"""
    logging.debug('cluster filtering')
    list_length = conf.getint('cluster', 'list_length')

    _db = DBConn(dict(conf.items('db')))
    await _db.connect()


    rda_dx_fname = conf.get('web', 'root') + '/json/dx.json'
    rda_dx = load_json(rda_dx_fname)
    prev = None
    if rda_dx:
        prev = rda_dx[0]
    else:
        rda_dx = []
    idx = 0
    with open(conf.get('files', 'cluster'), 'r') as fdx:
        with (await _db.pool.cursor()) as cur:
            for line in fdx:
                cs, freq, de, txt, dt, lotw, eqsl, cnt, band, country, _ = line.split('^')

                if prev and dt == prev['dt'] and prev['cs'] == cs:
                    break
                if 'Russia' in country:
                    rda = None
                    await exec_cur(cur, """
                            select rda 
                            from callsigns_rda
                            where callsign = %(cs)s and dt_stop is null
                        """, {'cs': cs})
                    if cur.rowcount == 1:
                        rda = (await cur.fetchone())[0]
                        item = DX(cs=cs, freq=freq, de=de, time=dt, text=txt, lotw=lotw, eqsl=eqsl, band=band)
                        item_d = item.toDict()
                        item_d['rda'] = rda
                        rda_dx.insert(idx, item_d)
                        idx += 1
            if idx > 0:
                if len(rda_dx) > list_length:
                    rda_dx = rda_dx[:list_length]
                save_json(rda_dx, rda_dx_fname)
    await _db.disconnect()

def main():
    """call from shell"""
    conf = site_conf()
    start_logging('cluster')

    asyncio.get_event_loop().run_until_complete(perform(conf))

if __name__ == "__main__":
    main()

