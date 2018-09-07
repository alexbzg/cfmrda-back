#!/usr/bin/python3
#coding=utf-8
"""functions for exporting stats data from db to frontend json files"""
import asyncio
import logging
import argparse

from common import site_conf, start_logging
from db import DBConn
from json_utils import save_json

@asyncio.coroutine
def export_rankings(conf):
    """export rankings data from db to json file for web"""
    logging.debug('export rankings')

    _db = DBConn(conf.items('db'))
    yield from _db.connect()

    rankings = {'hunters': {'bands': {}}, 'activators': {}}

    rankings['activators']['total'] = yield from _db.execute("""
        select activator as callsign, count(*),
            rank() over (order by count(*) desc)
        from (select activator, rda, count(distinct callsign)
            from qso
            group by activator, rda
            having count(distinct callsign) > 99) as rda_filter
        group by activator
        limit 100""", None, True)

    activators_bands = yield from _db.execute("""
        with bands_data as (select activator, count(rda) as rda_count, band, 
                    rank() over (partition by band order by count(rda) desc)
                from (select activator, rda, band, count(distinct callsign)
                    from qso
                    group by activator, rda, band
                    having count(distinct callsign) > 99) as rda_filter
                group by activator, band)
        select (select json_object_agg(band, data) from
        (select band, json_agg(json_build_object('callsign', activator, 'rank', rank)) 
        as data from bands_data group by band) as l0) as bands,
        (select json_agg(json_build_object('callsign', activator, 'rank', rank)) from
        (select activator, rank() over (order by sum(rda_count) desc) from bands_data
        group by activator limit 100) as l0_1) as bands_sum""")
    rankings['activators']['bands'] = activators_bands['bands']
    rankings['activators']['bandsSum'] = activators_bands['bands_sum']

    rankings['hunters']['total'] = yield from _db.execute("""
        select callsign, rank() over (order by count(distinct rda) desc) from
        (select callsign, rdas.rda from
        (WITH RECURSIVE t AS (
        (SELECT rda FROM qso ORDER BY rda LIMIT 1) 
        UNION ALL
        SELECT (SELECT rda FROM qso WHERE rda > t.rda ORDER BY rda LIMIT 1)
        FROM t
        WHERE t.rda IS NOT NULL
        )
        SELECT rda FROM t WHERE rda IS NOT NULL) as rdas, qso 
            where rdas.rda = qso.rda
        union 
        (select activator as callsign,
                        rda
                    from qso
                    group by activator, rda
                    having count(distinct callsign) > 99)) as rda_all
        group by callsign""", None, True)

    hunters_bands = yield from _db.execute("""
        with bands_data as (select callsign, band, count(distinct rda) as rda_count,
                    rank() over (partition by band order by count(distinct rda) desc)
                from
                (select callsign, band, qso.rda from
                (WITH RECURSIVE t AS (
                (SELECT rda FROM qso ORDER BY rda LIMIT 1)
                UNION ALL
                SELECT (SELECT rda FROM qso WHERE rda > t.rda ORDER BY rda LIMIT 1)
                FROM t
                WHERE t.rda IS NOT NULL
                )
                SELECT rda FROM t WHERE rda IS NOT NULL) as rdas, qso
                    where rdas.rda = qso.rda
                union
                (select activator as callsign, band, rda
                            from qso
                            group by activator, rda, band
                            having count(distinct callsign) > 99)) as rda_all
                group by callsign, band)
        select (select json_object_agg(band, data) from
        (select band, json_agg(json_build_object('callsign', callsign, 'rank', rank)) 
        as data from bands_data group by band) as l0) as bands,
        (select json_agg(json_build_object('callsign', callsign, 'rank', rank)) from
        (select callsign, rank() over (order by sum(rda_count) desc) from bands_data
        group by callsign) as l0_1) as bands_sum""")
    rankings['hunters']['bands'] = hunters_bands['bands']
    rankings['hunters']['bandsSum'] = hunters_bands['bands_sum']

    save_json(rankings, conf.get('web', 'root') + '/json/rankings.json')

def export_hunters(conf):
    """export detailed hunters stats from db to json file for web"""
    logging.debug('export hunters data')

    _db = DBConn(conf.items('db'))
    yield from _db.connect()

    data = yield from _db.execute("""
        select callsign, json_object_agg(rda, _data) as data from
        (select callsign, rda, json_object_agg(_type, _data) as _data from
        (select callsign, qso.rda, 
            json_agg(json_build_object('band', band, 'tstamp', qso.tstamp, 
                'stationCallsign', station_callsign, 'uploader', user_cs)) as _data, 
        'hunter' as _type
        from qso, uploads where qso.upload_id = uploads.id
        group by callsign, qso.rda
        union all
        select activator as callsign, rda, 
            json_agg(json_build_object('band', band, 'tstamp', tstamp, 'qsoCount', 
            qso_count, 'uploader', user_cs)) as _data, 'activator' as _type from
        (select qso.activator, qso.rda, user_cs, extract(day from qso.tstamp) as tstamp, 
            band, count(qso.id) as qso_count from
        (select activator, rda
                    from qso
                    group by activator, rda
                    having count(distinct callsign) > 99) as rda_filter, qso, uploads
        where rda_filter.activator = qso.activator and rda_filter.rda = qso.rda and 
            uploads.id = qso.upload_id
        group by qso.activator, qso.rda, user_cs, extract(day from qso.tstamp), band) as l0
        group by activator, rda) as u
        group by callsign, rda) as l1
        group by callsign             
            """, None, True)

    for row in data:
        save_json(row['data'],\
            conf.get('web', 'root') + '/json/hunters/' + row['callsign'] + '.json')

def main():
    """when called from shell exports rankings with -r, hunters with -d, all when no args"""
    start_logging('export')
    logging.debug('start export')
    conf = site_conf()
    parser = argparse.ArgumentParser()
    parser.add_argument('-r', action="store_true")
    parser.add_argument('-d', action="store_true")
    args = parser.parse_args()
    logging.debug(args)
    if args.r:
        asyncio.get_event_loop().run_until_complete(export_rankings(conf))
    if args.d:
        asyncio.get_event_loop().run_until_complete(export_hunters(conf))

if __name__ == "__main__":
    main()

