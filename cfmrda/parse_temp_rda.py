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

    rda_rus = requests.get('http://rdaward.org/rda_eng.txt').text

    params = []
    lines = rda_rus.split('\r\n')
    re_rda_line = re.compile(r'(^[A-Z][A-Z]-\d\d)\s+[^\t]+\t*(NEW RDA )?since (\d\d\.\d\d\.\d\d\d\d)(?: \(pre ([A-Z][A-Z]-\d\d)\)?')
    for line in lines:
        match_rda_line = re_rda_line.match(line)
        if match_rda_line:
            if match_rda_line.group(3):
                rda = match_rda_line.group(1)
                if rda == 'IR-03':
                    continue
                _dt = match_rda_line.group(3)
                prev = match_rda_line.group(4)
                if not match_rda_line.group(2):
                    params.append({\
                        'old': rda,\
                        'new': prev,\
                        'dt_start': _dt,\
                        'dt_stop': None\
                        })
                    params.append({\
                        'old': prev,\
                        'new': rda,\
                        'dt_start': None,\
                        'dt_stop': _dt\
                        })
                else:
                    params.append({\
                        'old': rda,\
                        'new': None,\
                        'dt_start': None,\
                        'dt_stop': _dt\
                        })
    logging.debug('populating old_rda table')
    yield from _db.execute("""insert into old_rda
        values (%(old)s, %(new)s, %(dt_start)s, %(dt_stop)s)""",\
        params, progress=True)

    params_qso = [x for x in params if x['new']]

    logging.debug('changing qsos rda')
    yield from _db.execute("""update qso
        set rda = %(new)s 
        where rda = %(old)s and 
            (tstamp >= %(dt_start)s or %(dt_start)s is null) and
            (tstamp <= %(dt_stop_s or %(dt_stop)s is null)""",\
        params_qso, progress=True)

asyncio.get_event_loop().run_until_complete(main())

