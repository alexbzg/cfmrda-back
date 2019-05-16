#!/usr/bin/python3
#coding=utf-8

import asyncio
import logging

from db import DBConn
from qrz import QRZRuLink
from common import site_conf

@asyncio.coroutine
def main():
    logger = logging.getLogger('')
    logger.setLevel(logging.DEBUG)
    conf = site_conf()
    _db = DBConn(conf.items('db'))
    yield from _db.connect()
    qrzru = QRZRuLink(asyncio.get_event_loop())

    callsigns = yield from _db.execute(\
        """select distinct hunter from rda_hunter""")
    logging.debug('callsigns list received')
    params = []
    for _cs in callsigns:
        data = yield from qrzru.query(_cs)
        if data and 'state' in data and data['state']:
            params.append({'callsign': _cs, 'rda': data['state']})
            logging.debug(_cs + ' found')
            break
        else:
            logging.debug(_cs + ' not found')
    logging.debug('qrz query complete')
    yield from _db.execute("""
            insert into callsigns_rda (callsign, source, rda)
            values (%(callsign)s, 'QRZ.ru', %(rda)s)""", params)

asyncio.get_event_loop().run_until_complete(main())

