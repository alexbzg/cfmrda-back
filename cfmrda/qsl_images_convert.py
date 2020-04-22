#!/usr/bin/python3
#coding=utf-8

import asyncio
import logging
import os

from db import DBConn
from common import site_conf

@asyncio.coroutine
def main():
    logger = logging.getLogger('')
    logger.setLevel(logging.DEBUG)
    conf = site_conf()
    _db = DBConn(conf.items('db'))
    yield from _db.connect()

    qsl_dir = conf.get('web', 'root') + '/qsl_images/'
    for file in os.listdir(qsl_dir):
        if os.path.isfile(qsl_dir + file):
            _id, rest = file.split('_', 1)
            new_id = yield from _db.execute("""
                select qsl_id 
                from cfm_qsl_qso 
                where id = %(id)s""", {'id': _id})
            if new_id:
                os.rename(qsl_dir + file, qsl_dir + str(new_id) + '_' + rest)

asyncio.get_event_loop().run_until_complete(main())

