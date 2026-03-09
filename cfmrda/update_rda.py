#!/usr/bin/python3
#coding=utf-8
"""populates db table of obsolete rdas"""

import asyncio
import logging
import re
import argparse

import requests
import yaml

from db import DBConn
from common import site_conf

async def main():
    logger = logging.getLogger('')
    logger.setLevel(logging.DEBUG)
    conf = site_conf()
    _db = DBConn(dict(conf.items('db')))
    await _db.connect()

    with open('/usr/local/cfmrda-dev/cfmrda/rda_update_2026_1.yaml', 'r') as rda_update_file:
        rda_update = yaml.safe_load(rda_update_file)

    old_rda_params = []
    add_rda_params = []
    replace_rda_params = []

    for entry in rda_update.get('add', []):
        for val in entry['values']:
            add_rda_params.append({'rda': val})
            if entry.get('start'):
                old_rda_params.append({'old': val, 'new': None, 'start': None, 'stop': entry['start']})

    for old, val in rda_update.get('replace', {}).items():
        params = {'old': old, 'new': None, 'start': None, 'stop': None}
        if isinstance(val, str):
            params['new'] = val
        else:
            params.update(val)
        old_rda_params.append(params)
        replace_rda_params.append(params)

    if add_rda_params:
        logging.debug('updating rda table')
        await _db.execute("""insert into rda
            (select %(rda)s 
            where not exists
            (select from rda where rda = %(rda)s))""",\
            add_rda_params, progress=True)

    if old_rda_params:
        logging.debug('updating old_rda table')
        await _db.execute("""insert into old_rda
            values (%(old)s, %(new)s, %(start)s, %(stop)s)""",\
            old_rda_params, progress=True)

    if replace_rda_params:
        logging.debug('changing qsos rda')
        await _db.execute("""update qso
            set rda = %(new)s where rda = %(old)s""",\
            replace_rda_params, progress=True)

        logging.debug('changing callsigns rda')
        await _db.execute("""update callsigns_rda
            set rda = %(new)s
            where rda = %(old)s""",\
            replace_rda_params, progress=True)

    delete_rda_params = [{'old': item} for item in rda_update.get('delete', [])]

    if delete_rda_params:
        logging.debug('deleting obsolete qsos')
        await _db.execute("""delete from qso
            where rda = %(old)s""",\
            delete_rda_params, progress=True)

        logging.debug('deleting obsolete callsigns rda')
        await _db.execute("""delete from callsigns_rda
            where rda = %(old)s""",\
            delete_rda_params, progress=True)


    if delete_rda_params or replace_rda_params:
        logging.debug('deleting obsolete rda')
        await _db.execute("""delete from rda
            where rda = %(old)s""",\
            delete_rda_params + replace_rda_params, progress=True)

asyncio.get_event_loop().run_until_complete(main())

