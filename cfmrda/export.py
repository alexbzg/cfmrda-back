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
    logging.debug('rankings table rebuilt')

    rankings = yield from _db.execute("""
                select rankings_json('_rank < 104') as data
                """, None, False)
    save_json(rankings, conf.get('web', 'root') + '/json/rankings.json')
    logging.debug('export rankings finished')

@asyncio.coroutine
def export_all(conf):
    yield from export_rankings(conf)
    yield from export_recent_uploads(conf)
    yield from export_msc(conf)

@asyncio.coroutine
def export_recent_uploads(conf):
    """export 20 recent uploaded file batches to json file for web"""
    logging.debug('export recent uploads')

    _db = DBConn(conf.items('db'))
    yield from _db.connect()

    data = yield from _db.execute("""
        select json_agg(json_build_object('activators', activators,
            'rda', rda,
            'uploadDate', to_char(max_tstamp, 'DD mon YYYY'),
            'uploadTime', to_char(max_tstamp, 'HH24:MI'),
            'uploadType', upload_type,
            'uploader', uploader)) as data
        from
        (select  user_cs as uploader, upload_type,
                max(tstamp) as max_tstamp,
                array_agg(id) as ids
            from uploads            
            group by date(tstamp), user_cs, upload_type
            order by max_tstamp desc
            limit 20) as ru,
        lateral 
        (select array_agg(distinct station_callsign) as activators 
            from qso 
            where upload_id = any(ids)) as acts,
        lateral 
        (select array_agg(rda) as rda   
            from 
                (select json_build_object('rda', array_agg(distinct rda), 
                        'id', upload_id) as rda 
                from qso 
                where upload_id = any(ids) 
                group by upload_id) as rdas0) as rdas 
        """, None, False)
    save_json(data, conf.get('web', 'root') + '/json/recent_uploads.json')
    logging.debug('export recent uploads finished')

@asyncio.coroutine
def export_msc(conf):
    """export misc db data to json file for web"""
    logging.debug('export misc')

    _db = DBConn(conf.items('db'))
    yield from _db.connect()

    data = {}
    data['qsoCount'] = (yield from _db.execute("""
        select count(*) as qso_count
        from qso;    
    """, None, False))
    save_json(data, conf.get('web', 'root') + '/json/msc.json')
    logging.debug('export misc finished')

def main():
    """when called from shell exports rankings"""
    start_logging('export')
    logging.debug('start export')
    conf = site_conf()

    def set_local_owner(file):
        """change exported file ownership when running as root"""
        if not os.getuid():
            shutil.chown(conf.get('web', 'root') + file,\
                user=conf.get('web', 'user'), group=conf.get('web', 'group'))

    parser = argparse.ArgumentParser()
    parser.add_argument('-r', action="store_true")
    parser.add_argument('-u', action="store_true")
    parser.add_argument('-m', action="store_true")
    args = parser.parse_args()
    export_all = not args.r and not args.u and not args.m
    if args.r or export_all:
        asyncio.get_event_loop().run_until_complete(export_rankings(conf))
        set_local_owner('/json/rankings.json')
    if args.u or export_all:
        asyncio.get_event_loop().run_until_complete(export_recent_uploads(conf))
        set_local_owner('/json/recent_uploads.json')
    if args.m or export_all:
        asyncio.get_event_loop().run_until_complete(export_msc(conf))
        set_local_owner('/json/msc.json')

if __name__ == "__main__":
    main()

