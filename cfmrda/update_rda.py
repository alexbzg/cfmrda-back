#!/usr/bin/python3
#coding=utf-8
"""populates db table of obsolete rdas"""

import asyncio
import logging
import re
import argparse

import requests
from yaml import load

from db import DBConn
from common import site_conf

async def main():
    logger = logging.getLogger('')
    logger.setLevel(logging.DEBUG)
    conf = site_conf()
    _db = DBConn(conf.items('db'))
    #await _db.connect()
    #await _db.execute('delete from old_rda;')

    rda_update = load('/usr/local/cfmrda-dev/cfmrda/rda_update_2025')

    params_old = []
    params = []

    with open('/var/www/cfmrda/files/csv/rda.csv', 'w') as fcsv:
        for group in groups:
            fcsv.write('{id};;{title};\n'.format_map(group))
            for val in group['values']:
                fcsv.write(';{val};{title};{id}\n'.format_map(val))

    with open('/var/www/cfmrda/files/csv/rda_old_new.csv', 'w') as fcsv:
        for item in params_old:
            if item['new']:
                fcsv.write('{old};{new}\n'.format_map(item))
    logging.debug('csv created')

    rda_changed = [i for i in params_old if i['new']]
    rda_deleted = [i for i in params_old if not i['new']]

    old_rda_params = []
    add_rda_params = []

    for entry in rda_update.get('add', []):
        for val, title in entry['values'].items():
            add_rda_params.append({'rda': val})
            if entry.get('start'):
                old_rda_params.appens({'old': val, 'new': None, 'stop': entry['start']})

    logging.debug('updating rda table')
    await _db.execute("""insert into rda
        (select %(rda)s 
        where not exists
        (select from rda where rda = %(rda)s))""",\
        params, progress=True)

    logging.debug('updating old_rda table')
    await _db.execute("""insert into old_rda
        values (%(old)s, %(new)s)""",\
        params_old, progress=True)

    replace_rda_params = []
    for old, new in rda_update.get('replace', {}):
        replace_rda_params.append({'old': old, 'new': new})
    
    logging.debug('changing qsos rda')
    await _db.execute("""update qso
        set rda = %(new)s where rda = %(old)s""",\
        replace_rda_params, progress=True)

    logging.debug('changing callsigns rda')
    await _db.execute("""update callsigns_rda
        set rda = %(new)s
        where rda = %(old)s""",\
        replace_rda_params, progress=True)

    for item in rda_update.get('delete', []):
        replace_rda_params.append({'old': item})

    logging.debug('deleting obsolete qsos')
    await _db.execute("""delete from qso
        where rda = %(old)s""",\
        replace_rda_params, progress=True)

    logging.debug('deleting obsolete callsigns rda')
    await _db.execute("""delete from callsigns_rda
        where rda = %(old)s""",\
        replace_rda_params, progress=True)

    logging.debug('deleting obsolete rda')
    await _db.execute("""delete from rda
        where rda = %(old)s""",\
        replace_rda_params, progress=True)

asyncio.get_event_loop().run_until_complete(main())

