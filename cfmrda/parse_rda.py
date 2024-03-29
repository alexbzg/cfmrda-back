#!/usr/bin/python3
#coding=utf-8
"""populates db table of obsolete rdas"""

import asyncio
import logging
import re

import requests

from db import DBConn
from common import site_conf

async def main():
    logger = logging.getLogger('')
    logger.setLevel(logging.DEBUG)
    conf = site_conf()
    _db = DBConn(conf.items('db'))
    #await _db.connect()
    #await _db.execute('delete from old_rda;')

    rda_rus = requests.get('https://rdaward.ru/rda_list.php?lang=en').text

    params_old = []
    params = []
    lines = rda_rus.split('\r\n')
    re_rda_line = re.compile(r'(^[A-Z][A-Z]-\d\d)\s+([^\t]+)\t*((?:\*\*\*)?[A-Z][A-Z]-\d\d|\*\*\*)?')
    re_group_line = re.compile(r'\s*(\w.*\(([A-Z][A-Z])\)\s+\w\w\w\w)$')
    groups = []
    group = None
    for line in lines:
        match_group_line = re_group_line.match(line)
        if match_group_line:
            if group and group['values']:
                groups.append(group)
            group_id = 'RK' if 'UA6K' in line else match_group_line.group(2)
            group = {\
                    'id': group_id,\
                    'title': match_group_line.group(1),\
                    'values': []}
        else:
            match_rda_line = re_rda_line.match(line)
            if match_rda_line:
                if match_rda_line.group(3):
                    old = match_rda_line.group(1)
                    new = None
                    if old != 'IR-03':
                        new = None if match_rda_line.group(3) == '***' else match_rda_line.group(3)
                    if new:
                        new = new.replace('*', '')
                    params_old.append({'old': old, 'new': new})
                else:
                    params.append({'rda': match_rda_line.group(1)})
                    group['values'].append({'id': match_rda_line.group(1),\
                            'title': match_rda_line.group(2),
                            'val':match_rda_line.group(1)[-2:].lstrip('0')})
    if group and group['values']:
        groups.append(group)

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

    logging.debug('populating old_rda table')
    #await _db.execute("""insert into old_rda
    #    values (%(old)s, %(new)s)""",\
    #    params_old, progress=True)

    rda_changed = [i for i in params_old if i['new']]
    rda_deleted = [i for i in params_old if not i['new']]

    return
    logging.debug('adding new rda')
    await _db.execute("""insert into rda
        (select %(rda)s 
        where not exists
        (select from rda where rda = %(rda)s))""",\
        params, progress=True)

    logging.debug('changing qsos rda')
    await _db.execute("""update qso
        set rda = %(new)s where rda = %(old)s""",\
        rda_changed, progress=True)

    logging.debug('deleting obsolete qsos')
    await _db.execute("""delete from qso
        where rda = %(old)s""",\
        rda_deleted, progress=True)

    logging.debug('deleting obsolete callsigns rda')
    await _db.execute("""delete from callsigns_rda
        where rda = %(old)s""",\
        rda_deleted, progress=True)

    logging.debug('changing callsigns rda')
    await _db.execute("""update callsigns_rda
        set rda = %(new)s
        where rda = %(old)s""",\
        rda_changed, progress=True)

    logging.debug('deleting obsolete rda')
    await _db.execute("""delete from rda
        where rda = %(old)s""",\
        rda_deleted, progress=True)

asyncio.get_event_loop().run_until_complete(main())

