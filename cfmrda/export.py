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

@asyncio.coroutine
def export_recent_uploads(conf):
    """export 20 recent uploaded file batches to json file for web"""
    logging.debug('export recent uploads')

    _db = DBConn(conf.items('db'))
    yield from _db.connect()

    data = (yield from _db.execute("""
        select json_agg(json_build_object('activators', activators,
            'rda', rda,
            'uploadDate', to_char(tstamp, 'DD mon YYYY'),
            'uploadTime', to_char(tstamp, 'HH24:MI'),
            'uploader', uploader)) as data
        from
            (select json_agg(distinct activators) as activators, user_cs as uploader,
                json_agg(json_build_object('rda', rdas, 'id', id)) as rda,
                max(tstamp) as tstamp,
                min(date_start) as date_start, max(date_end) as date_end
            from uploads,
                (select upload_id, rdas, unnest(activators) as activators
                from
                    (select upload_id, array_agg(distinct rda) as rdas,
                        array_agg(distinct station_callsign) as activators
                    from qso
                    group by upload_id) as act_l_0) as activators
            where uploads.id = activators.upload_id
            group by user_cs, date(tstamp)
            order by max(tstamp) desc
            limit 20) as data
        """, None, False))['data']
    save_json(data, conf.get('web', 'root') + '/json/recent_uploads.json')

@asyncio.coroutine
def export_msc(conf):
    """export misc db data to json file for web"""
    logging.debug('export misc')

    _db = DBConn(conf.items('db'))
    yield from _db.connect()

    data = {}
    data['qsoCount'] = (yield from _db.execute("""
        select n_live_tup AS qso_count
        from pg_stat_user_tables 
        where relname = 'qso' and schemaname = 'public';    
    """, None, False))['qso_count']
    save_json(data, conf.get('web', 'root') + '/json/msc.json')

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
    export_all = not args.r and not args.u
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

