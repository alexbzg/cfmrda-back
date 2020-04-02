#!/usr/bin/python3
#coding=utf-8

import asyncio
import logging
import logging.handlers
import re

from db import DBConn, CfmrdaDbException
from qrz import QRZRuLink
from common import site_conf
from ham_radio import Pfx, detect_rda

RE_SPECIAL = re.compile(r'\d\d')


@asyncio.coroutine
def main():
    logger = logging.getLogger('')
    handler = logging.handlers.WatchedFileHandler('/var/log/cfmrda.qrz.log')
    handler.setFormatter(logging.Formatter(\
        '%(asctime)s %(name)-12s %(levelname)-8s %(message)s'))
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    handler.setLevel(logging.DEBUG)

    conf = site_conf()
    _db = DBConn(conf.items('db'))
    yield from _db.connect()
    qrzru = QRZRuLink(asyncio.get_event_loop())
    pfx = Pfx('/usr/local/webcluster/cty.dat')

    @asyncio.coroutine
    def db_write(data):
        try:
            yield from _db.execute("""
                insert into callsigns_rda (callsign, source, rda)
                values (%(callsign)s, 'QRZ.ru', %(rda)s)""", data)
        except CfmrdaDbException:
            pass

    callsigns = yield from _db.execute(\
        """select distinct hunter from rda_hunter
            where not exists
                (select from callsigns_rda
                where callsign = hunter and
                    source = 'QRZ.ru' and ts > now() - interval '2 days)'
        """)
    logging.debug('callsigns list received -- ' + str(len(callsigns)))
    params = []
    cnt = 0
    ru_cnt = 0
    fnd_cnt = 0
    for _cs in callsigns:
        cnt += 1
        cs_pfx = pfx.get(_cs)
        if cs_pfx in ['R', 'R2F', 'R9']:
            m_special = RE_SPECIAL.search(_cs)
            if m_special:
                continue
            ru_cnt += 1
            data = yield from qrzru.query(_cs)
            if data and 'state' in data and data['state']:
                rda = detect_rda(data['state'])
                fnd_cnt += 1
                yield from db_write({'callsign': _cs, 'rda': rda})
                logging.debug(_cs + ' found')
                if len(params) >= 100:
                    logging.debug('Processed ' + str(cnt) + '/' + str(ru_cnt) + '/'\
                        + str(fnd_cnt) + ' of ' + str(len(callsigns)))
        cnt += 1
    logging.debug('qrz query complete')

asyncio.get_event_loop().run_until_complete(main())

