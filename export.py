#!/usr/bin/python3
#coding=utf-8
"""functions for exporting stats data from db to frontend json files"""
import asyncio
import logging
import argparse
import os
import shutil
import datetime
from cfmrda.common import site_conf, start_logging
from cfmrda.db import DBConn
from cfmrda.utils.json_utils import save_json, load_json

CONF = site_conf()

def set_local_owner(file):
    """change exported file ownership when running as root"""
    if not os.getuid():
        shutil.chown(CONF.get('web', 'root') + file,\
            user=CONF.get('web', 'user'), group=CONF.get('web', 'group'))

async def export_rankings(export_only=False):
    """rebuild rankings table in db and export top100 to json file for web"""
    logging.debug('export rankings')

    db_params = dict(CONF.items('db'))
    db_params.update(dict(CONF.items('db_maintenance')))
    _db = DBConn(db_params)
    do_maint = datetime.datetime.now().weekday() == 3
    do_countries = True #do_maint
    await _db.connect()

    msc_json_path = CONF.get('web', 'root') + '/json/msc.json'
    def update_msc_data(**upd_data):
        msc_data = load_json(msc_json_path) or {}
        msc_data.update(upd_data)
        save_json(msc_data, msc_json_path)

    update_msc_data(statsDate=None)

    if not export_only:
        await _db.execute('select from build_rankings_purge_rda();')
        if do_maint:
            await _db.execute("vacuum full freeze verbose analyze rda_activator;")
            logging.debug('export rankings: rda_activator table vacuumed')
            await _db.execute("vacuum full freeze verbose analyze rda_hunter;")
            logging.debug('export rankings: rda_hunter table vacuumed')

        await _db.execute('select from build_rankings_activator_data();')

        if do_maint:
            await _db.execute('delete from rankings;')
            await _db.execute("vacuum full freeze verbose analyze rankings;")
            logging.debug('export rankings: rankings table vacuumed')
            await _db.execute('delete from activators_rating_current;')
            await _db.execute("vacuum full freeze verbose analyze activators_rating_current;")
            logging.debug('export rankings: activators_rating_current table vacuumed')
            await _db.execute('delete from activators_rating_current_detail;')
            await _db.execute("vacuum full freeze verbose analyze activators_rating_current_detail;")
            logging.debug('export rankings: activators_rating_current_detail table vacuumed')
            await _db.execute('delete from activators_rating_tmp;')
            await _db.execute("vacuum full freeze verbose analyze activators_rating_tmp;")
            logging.debug('export rankings: activators_rating_tmp table vacuumed')

            await _db.execute("vacuum full freeze verbose analyze qso;")
            logging.debug('export rankings: qso table vacuumed')

        await _db.execute("select from build_rankings_main();")

        if do_countries:
            await _db.execute("select from build_rankings_countries();")

        await _db.execute("select from build_activators_rating_current();")

    rankings = await _db.execute("""
                select rankings_json(null, null, null, null, 105, null, null) as data
                """, None, False)

    save_json(rankings, CONF.get('web', 'root') + '/json/rankings.json')
    set_local_owner('/json/rankings.json')

    if do_countries:
        countries = await _db.execute("""select id from countries""", None, False)
        for country in countries:
            json_path = '/json/countries_rankings/' + str(country) + '.json'
            rankings = await _db.execute("""
                    select rankings_json(null, null, null, null, 104, null, %(id)s) as data
                    """, {'id': country}, False)
            save_json(rankings, CONF.get('web', 'root') + json_path)
            set_local_owner(json_path)

    logging.debug('export rankings finished')

    logging.debug('export qso count')

    msc_data = load_json(msc_json_path) or {}
    save_json(msc_data, msc_json_path)

    update_msc_data(statsDate=datetime.datetime.utcnow().strftime('%d %b %Y %H:%Mz'))

    qso_count = await _db.execute("""
        select count(*) as qso_count
        from qso;    
    """, None, False)

    update_msc_data(qsoCount=qso_count)
    logging.debug('export qso count finished')

async def export_callsigns():
    """export distinct callsigns into json array"""
    logging.debug('export callsigns')

    _db = DBConn(dict(CONF.items('db')))
    await _db.connect()


    callsigns = await _db.execute("""
        select distinct hunter from rda_hunter as h0
        where (select count(*) from rda_hunter as h1
            where h0.hunter = h1.hunter) > 4
        """, None, False)
    save_json(callsigns, CONF.get('web', 'root') + '/json/callsigns.json')
    logging.debug('export callsigns finished')

async def export_recent_uploads():
    """export 20 recent uploaded file batches to json file for web"""
    logging.debug('export recent uploads')

    _db = DBConn(dict(CONF.items('db')))
    await _db.connect()

    data = await _db.execute("""
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
    save_json(data, CONF.get('web', 'root') + '/json/recent_uploads.json')
    logging.debug('export recent uploads finished')

async def export_msc():
    """export misc db data to json file for web"""
    logging.debug('export misc')

    _db = DBConn(dict(CONF.items('db')))
    await _db.connect()

    json_path = CONF.get('web', 'root') + '/json/msc.json'
    data = load_json(json_path) or {}

    data['unsortedQsl'] = (await _db.execute("""
        select count(*) as qsl_wait 
        from cfm_qsl_qso 
        where state is null;
    """, None, False))

    data['userActivity'] = (await _db.execute("""
        with qsl_data as 
            (select user_cs, state 
            from cfm_qsl_qso, cfm_qsl
            where cfm_qsl.id = cfm_qsl_qso.qsl_id)
        select json_agg(data) from
            (select json_build_object('callsign', 
                coalesce(qsl_wait.callsign, qsl_today.callsign), 
                'qslWait', qsl_wait, 'qslToday', qsl_today) as data 
            from
                (select user_cs as callsign, count(*) as qsl_wait 
                from qsl_data
                where state is null 
                group by user_cs) as qsl_wait 
                full join
                (select user_cs as callsign, count(*) as qsl_today 
                from qsl_data
                where state
                group by user_cs) as qsl_today 
                on qsl_wait.callsign = qsl_today.callsign 
                order by coalesce(qsl_wait.callsign, qsl_today.callsign)
            )  as data""", None, False))

    save_json(data, json_path)
    logging.debug('export misc finished')

async def export_stat():
    """export statistic data to json file for web"""
    logging.debug('export stats')

    _db = DBConn(dict(CONF.items('db')))
    await _db.connect()

    data = {}
    data['qso by rda'] = (await _db.execute("""
        select json_object_agg(rda, data) as data from
            (select rda, json_object_agg(band, data) as data from
                (select rda, band, json_object_agg(mode, qso_count) as data from
                    (select count(*) as qso_count, rda, band, mode 
                    from qso left join uploads on upload_id = uploads.id
                    where upload_id is null or enabled   
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
    save_json(data, CONF.get('web', 'root') + '/json/stat.json')
    logging.debug('export stats finished')

def main():
    """when called from shell exports rankings"""
    start_logging('export')
    logging.debug('start export')


    parser = argparse.ArgumentParser()
    parser.add_argument('-r', action="store_true")
    parser.add_argument('-u', action="store_true")
    parser.add_argument('-m', action="store_true")
    parser.add_argument('-s', action="store_true")
    parser.add_argument('-c', action="store_true")
    parser.add_argument('--export_only', action="store_true")
    args = parser.parse_args()
    export_all = not args.r and not args.u and not args.m and not args.s and not args.c
    if args.r or export_all:
        asyncio.get_event_loop().run_until_complete(export_rankings(args.export_only))
        set_local_owner('/json/msc.json')
    if args.u or export_all:
        asyncio.get_event_loop().run_until_complete(export_recent_uploads())
        set_local_owner('/json/recent_uploads.json')
    if args.m or export_all:
        asyncio.get_event_loop().run_until_complete(export_msc())
        set_local_owner('/json/msc.json')
    if args.s or export_all:
        asyncio.get_event_loop().run_until_complete(export_stat())
        set_local_owner('/json/stat.json')
    if args.c:
        asyncio.get_event_loop().run_until_complete(export_callsigns())
        set_local_owner('/json/callsigns.json')



if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logging.exception('Export exception')
