#!/usr/bin/python3
#coding=utf-8
"""functions for exporting stats data from db to frontend json files"""
import asyncio
import logging
import argparse
import os
import shutil

from common import site_conf, start_logging
from db import DBConn
from json_utils import save_json

@asyncio.coroutine
def export_rankings(conf):
    """rebuild rankings table in db and export top100 to json file for web"""
    logging.debug('export rankings')

    _db = DBConn(conf.items('db'))
    yield from _db.connect()

    yield from _db.execute("select from build_rankings()")

    rankings = (yield from _db.execute("""
                select rankings_json('_rank < 101') as data
                """, None, False))['data']
    save_json(rankings, conf.get('web', 'root') + '/json/rankings.json')

def main():
    """when called from shell exports rankings"""
    start_logging('export')
    logging.debug('start export')
    conf = site_conf()
#    parser = argparse.ArgumentParser()
#    parser.add_argument('-r', action="store_true")
#    parser.add_argument('-d', action="store_true")
#    args = parser.parse_args()
#    export_all = not args.r and not args.d
#    if args.r or export_all:
    asyncio.get_event_loop().run_until_complete(export_rankings(conf))
    if not os.getuid():
        shutil.chown(conf.get('web', 'root') + '/json/rankings.json',\
            user=conf.get('web', 'user'), group=conf.get('web', 'group'))

if __name__ == "__main__":
    main()

