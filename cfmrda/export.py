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

    rankings = {'hunters': {'total': {}, 'modes': {}}, 
            'activators': {'total': {}, 'modes': {}}}

    rankings['activators']['total']['total'] = yield from _db.execute("""
        select activator as callsign, count(*),
            rank() over (order by count(*) desc)
        from (select activator, rda, count(distinct callsign)
            from qso
            group by activator, rda
            having count(distinct callsign) > 99) as rda_filter
        group by activator
        limit 100""", None, True)

   rankings['activators']['total']['modes'] = yield from _db.execute("""
        select json_build_object(mode, json_agg(json_build_object(
            'callsign', callsign, 'count', count, 'rank', rank))) 
        from (select activator as callsign, mode, count(*),
                    rank() over (partition by mode order by count(*) desc)
                from (select activator, rda, mode, count(distinct callsign)
                    from qso
                    group by activator, rda, mode
                    having count(distinct callsign) > 99) as rda_filter
                group by activator, mode
                ) as l_0
        where rank < 101
        group by mode
        """, None, True)

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
         select callsign, rank() over (order by count(distinct rda) desc),
            count(distinct rda) from
        (select callsign, rda from qso
        union all 
        (select activator as callsign,
                        rda
                    from qso
                    group by activator, rda
                    having count(distinct callsign) > 99)) as rda_all
        group by callsign        
            """, None, True)

    hunters_bands = yield from _db.execute("""
         with bands_data as (select callsign, band, count(distinct rda),
                    rank() over (partition by band order by count(distinct rda) desc)
                from
                (select callsign, band, rda from qso
                union all
                (select activator as callsign, band, rda
                            from qso
                            group by activator, rda, band
                            having count(distinct callsign) > 99)) as rda_all
                group by callsign, band)
        select (select json_object_agg(band, data) from
        (select band, json_agg(json_build_object('callsign', callsign, 'rank', rank,
            'count', count))
        as data from bands_data group by band) as l0) as bands,
        (select json_agg(json_build_object('callsign', callsign, 'rank', rank, 'count', count)) from
        (select callsign, rank() over (order by sum(count) desc), sum(count) as count from bands_data
        group by callsign) as l0_1) as bands_sum        
            """)
    rankings['hunters']['bands'] = hunters_bands['bands']
    rankings['hunters']['bandsSum'] = hunters_bands['bands_sum']

    save_json(rankings, conf.get('web', 'root') + '/json/rankings.json')

def export_hunters(conf):
    """export detailed hunters stats from db to json file for web"""
    logging.debug('export hunters data')

    _db = DBConn(conf.items('db'))
    yield from _db.connect()

    data = yield from _db.execute("""
        WITH RECURSIVE cs AS (
        (SELECT callsign FROM qso ORDER BY callsign LIMIT 1)
        UNION ALL
        SELECT (SELECT callsign FROM qso WHERE callsign > cs.callsign ORDER BY callsign LIMIT 1)
        FROM cs
        WHERE cs.callsign IS NOT NULL)
        SELECT callsign, 
        (select json_object_agg(rda, 
            (select json_object_agg(band, data) from
            (select band, json_agg(json_build_object('band', band, 'tstamp', qso.tstamp,
                    'date', to_char(qso.tstamp, 'DD Month YYYY'), 
                    'time', to_char(qso.tstamp, 'HH24:MI'), 'mode', mode,
                        'stationCallsign', station_callsign, 'uploader', user_cs)) as data 
                from qso, uploads where qso.callsign = cs.callsign and qso.rda = rdas_1.rda 
                and qso.upload_id = uploads.id
                group by band) as bands_0))
        from (WITH RECURSIVE rdas AS (
        (SELECT rda FROM qso where qso.callsign = cs.callsign ORDER BY rda LIMIT 1)
        UNION ALL
        SELECT (SELECT rda FROM qso WHERE rda > rdas.rda and 
            qso.callsign = cs.callsign ORDER BY rda LIMIT 1)
        FROM rdas
        WHERE rda IS NOT NULL)
        select rda from rdas where rda is not null) as rdas_1) as data
        FROM cs WHERE callsign IS NOT NULL
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
    export_all = not args.r and not args.d
    if args.r or export_all:
        asyncio.get_event_loop().run_until_complete(export_rankings(conf))
    if args.d or export_all:
        asyncio.get_event_loop().run_until_complete(export_hunters(conf))

if __name__ == "__main__":
    main()

