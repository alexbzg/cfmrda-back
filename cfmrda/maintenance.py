#!/usr/bin/python3
#coding=utf-8
"""functions for exporting stats data from db to frontend json files"""
import asyncio
import logging

from common import site_conf, start_logging
from db import DBConn

@asyncio.coroutine
def perform(conf):
    """db maintenance"""
    logging.debug('start maintenance')

    _db = DBConn(conf.items('db'))
    yield from _db.connect()

#    yield from _db.execute("delete from cfm_request_qso where state")
#    logging.debug('confirmed email cfm requests deleted')

    yield from _db.execute("delete from cfm_qsl_qso where state")
    logging.debug('confirmed qsl cfm requests deleted')

    yield from _db.execute("delete from activators where not exists (select from qso where qso.upload_id = activators.upload_id)")
    yield from _db.execute("delete from uploads where not exists (select from qso where qso.upload_id = uploads.id)")
    logging.debug('empty uploads deleted')

    logging.debug('maintenance finished')

def main():
    """call from shell"""
    conf = site_conf()
    start_logging('maintenance')

    asyncio.get_event_loop().run_until_complete(perform(conf))

if __name__ == "__main__":
    main()

