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
def export_callsigns(conf):
    """export distinct callsigns into json array"""
    logging.debug('export callsigns')

    _db = DBConn(conf.items('db'))
    yield from _db.connect()


    callsigns = yield from _db.execute("""
                select array_agg(callsign) 
                from (
                    select distinct callsign
                    from qso) as cs
                """, None, False)
    save_json(callsigns, conf.get('web', 'root') + '/json/callsigns.json')
    logging.debug('export rankings finished')

@asyncio.coroutine
def export_recent_uploads(conf):
    """export 20 recent uploaded file batches to json file for web"""
    logging.debug('export recent uploads')

    _db = DBConn(conf.items('db'))
    yield from _db.connect()

    data = yield from _db.execute("""
        select json_agg(json_build_object(
            'activators', activators,
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
            where ext_logger_id is null
            group by date(tstamp), user_cs, upload_type
            order by max_tstamp desc
            limit 40) as ru,
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

    data['unsortedQsl'] = (yield from _db.execute("""
        select count(*) as qsl_wait 
        from cfm_qsl_qso 
        where state is null;
    """, None, False))

    data['userActivity'] = (yield from _db.execute("""
        select json_agg(data) from
            (select json_build_object('callsign', 
                coalesce(qsl_wait.callsign, qsl_today.callsign, email.callsign), 
                'qslWait', qsl_wait, 'qslToday', qsl_today, 
                'email', email) as data 
            from
                (select user_cs as callsign, count(*) as qsl_wait 
                from cfm_qsl_qso 
                where state is null 
                group by user_cs) as qsl_wait 
                full join
                (select user_cs as callsign, count(*) as qsl_today 
                from cfm_qsl_qso 
                where state
                group by user_cs) as qsl_today 
                on qsl_wait.callsign = qsl_today.callsign 
                full join
                (select user_cs as callsign, count(*) as email 
                from cfm_request_qso 
                where not sent and user_cs is not null  
                group by user_cs) as email 
                on coalesce(qsl_wait.callsign, qsl_today.callsign) = email.callsign
                order by coalesce(qsl_wait.callsign, qsl_today.callsign, 
                    email.callsign)
            )  as data""", None, False))

    save_json(data, conf.get('web', 'root') + '/json/msc.json')
    logging.debug('export misc finished')

@asyncio.coroutine
def export_stat(conf):
    """export statistic data to json file for web"""
    logging.debug('export stats')

    _db = DBConn(conf.items('db'))
    yield from _db.connect()

    data = {}
    data['qso by rda'] = (yield from _db.execute("""
        select json_object_agg(rda, data) as data from
            (select rda, json_object_agg(band, data) as data from
                (select rda, band, json_object_agg(mode, qso_count) as data from
                    (select count(*) as qso_count, rda, band, mode 
                    from qso 
                    where upload_id is null or 
                        (select enabled from uploads 
                        where id=upload_id) 
                    group by mode, band, rda
                    ) as q0
                group by rda, band) as q1
            group by rda) as q2
    """, None, False))
    for rda_data in data['qso by rda'].values():
        rda_total = {'total': 0}
        for band_data in rda_data.values():
            band_total = 0
            for mode, qso_count in band_data.items():
                band_total += qso_count
                if mode not in rda_total:
                    rda_total[mode] = 0
                rda_total[mode] += qso_count
            band_data['total'] = band_total
            rda_total['total'] += band_total
        rda_data['total'] = rda_total
    save_json(data, conf.get('web', 'root') + '/json/stat.json')
    logging.debug('export stats finished')

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
    parser.add_argument('-s', action="store_true")
    parser.add_argument('-c', action="store_true")
    args = parser.parse_args()
    export_all = not args.r and not args.u and not args.m and not args.s
    if args.r or export_all:
        asyncio.get_event_loop().run_until_complete(export_rankings(conf))
        set_local_owner('/json/rankings.json')
    if args.u or export_all:
        asyncio.get_event_loop().run_until_complete(export_recent_uploads(conf))
        set_local_owner('/json/recent_uploads.json')
    if args.m or export_all:
        asyncio.get_event_loop().run_until_complete(export_msc(conf))
        set_local_owner('/json/msc.json')
    if args.s or export_all:
        asyncio.get_event_loop().run_until_complete(export_stat(conf))
        set_local_owner('/json/stat.json')
    if args.c:
        asyncio.get_event_loop().run_until_complete(export_callsigns(conf))
        set_local_owner('/json/callsigns.json')



if __name__ == "__main__":
    main()

