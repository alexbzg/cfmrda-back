#!/usr/bin/python3
#coding=utf-8
"""populates db table of obsolete rdas"""

import asyncio
import logging

from db import DBConn
from common import site_conf

@asyncio.coroutine
def main():
    logger = logging.getLogger('')
    logger.setLevel(logging.DEBUG)
    conf = site_conf()
    _db = DBConn(conf.items('db'))
    yield from _db.connect()

    with open('/var/www/adxc.test/csv/rda_old_new.csv', 'r') as f_data:
        params = []
        for line in f_data.readlines():
            fields = {}
            fields['old'], fields['new'] = line.strip().split(';')
            if fields['old'] and fields['new']:
                params.append(fields)

        yield from _db.execute("""insert into old_rda
            values (%(old)s, %(new)s)""",\
            params, progress=True)

asyncio.get_event_loop().run_until_complete(main())

