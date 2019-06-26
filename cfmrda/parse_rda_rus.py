#!/usr/bin/python3
#coding=utf-8
"""populates db table of obsolete rdas"""

import asyncio
import logging
import re

import requests

from db import DBConn
from common import site_conf

@asyncio.coroutine
def main():
    logger = logging.getLogger('')
    logger.setLevel(logging.DEBUG)
    conf = site_conf()
    _db = DBConn(conf.items('db'))
    yield from _db.connect()
    yield from _db.execute('delete from old_rda;')
    yield from _db.execute('delete from rda;')

    rda_rus = requests.get('http://rdaward.org/rda_rus.txt').text

    params_old = []
    params = []
    lines = rda_rus.split('\r\n')
    re_rda_line = re.compile(r'(^[A-Z][A-Z]-\d\d)\s+[^\t]+\t*([A-Z][A-Z]-\d\d|\*\*\*)?')
    for line in lines:
        match_rda_line = re_rda_line.match(line)
        if match_rda_line:
            if match_rda_line.group(2):
                old = match_rda_line.group(1)
                new = None if match_rda_line.group(2) == '***' else match_rda_line.group(2)
                params_old.append({'old': old, 'new': new})
            else:
                params.append({'rda': match_rda_line.group(1)})

    yield from _db.execute("""insert into old_rda
        values (%(old)s, %(new)s)""",\
        params_old, progress=True)

    yield from _db.execute("""insert into rda
        values (%(rda)s)""",\
        params, progress=True)

asyncio.get_event_loop().run_until_complete(main())

