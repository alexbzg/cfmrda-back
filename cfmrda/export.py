#!/usr/bin/python3
#coding=utf-8
"""functions for exporting stats data from db to frontend json files"""
import asyncio
import logging

from common import site_conf, start_logging
from db import DBConn
from json_utils import save_json
from ham_radio import BANDS

@asyncio.coroutine
def export_rankings(conf):
    """export rankings data from db to json file for web"""
    logging.debug('export rankings')

    _db = DBConn(conf.items('db'))
    yield from _db.connect()

    rankings = {'hunters': {'bands': {}}, 'activators': {'bands': {}}}
    for band in BANDS:
        rankings['hunters']['bands'][band] = []
        rankings['activators']['bands'][band] = []

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
        select activator, band, count(rda) as rda_count,
            rank() over (partition by band order by count(rda) desc)
        from (select activator, rda, band, count(distinct callsign)
            from qso
            group by activator, rda, band
            having count(distinct callsign) > 99) as rda_filter
        group by activator, band""", None, True)
    for row in activators_bands:
        rankings['activators']['bands'][row['band']].append(\
            {'callsign': row['activator'], 'rank': row['rank']})

    rankings['activators']['bandsSum'] = yield from _db.execute("""
        select activator as callsign, count(rda) as rda_count,
            rank() over (order by count(rda) desc)
        from (select activator, rda, band, count(distinct callsign)
            from qso
            group by activator, rda, band
            having count(distinct callsign) > 99) as rda_filter
        group by activator""", None, True)

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
        select callsign, band, 
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
        group by callsign, band
""", None, True)
    for row in hunters_bands:
        rankings['hunters']['bands'][row['band']].append(\
            {'callsign': row['callsign'], 'rank': row['rank']})

    rankings['hunters']['bandsSum'] = yield from _db.execute("""
        select callsign, 
            rank() over (order by count(distinct band || '*' || rda) desc) 
        from (select callsign, band, qso.rda from
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
        group by callsign""", None, True)

    save_json(rankings, conf.get('web', 'root') + '/json/rankings.json')

def export_hunters(conf):
    """export detailed hunters stats from db to json file for web"""
    logging.debug('export hunters data')

    _db = DBConn(conf.items('db'))
    yield from _db.connect()

    data = yield from _db.execute("""
        select callsign, json_object_agg(rda, bands) as data from
        (select callsign, rda, json_object_agg(band, qsos) as bands from
        (select callsign, rdas.rda, bands.band, 
            json_agg(json_build_object('activator', station_callsign, 'tstamp', qso.tstamp, 
                'uploader', user_cs)) as qsos from
        (WITH RECURSIVE t AS (
                (SELECT band FROM qso ORDER BY band LIMIT 1)
                UNION ALL
                SELECT (SELECT band FROM qso WHERE band > t.band ORDER BY band LIMIT 1)
                FROM t
                WHERE t.band IS NOT NULL
                )
                SELECT band FROM t WHERE band IS NOT NULL) as bands,
        (WITH RECURSIVE t AS (
                (SELECT rda FROM qso ORDER BY rda LIMIT 1)
                UNION ALL
                SELECT (SELECT rda FROM qso WHERE rda > t.rda ORDER BY rda LIMIT 1)
                FROM t
                WHERE t.rda IS NOT NULL
                )
                SELECT rda FROM t WHERE rda IS NOT NULL) as rdas, qso, uploads
        where qso.band = bands.band and qso.rda = rdas.rda and uploads.id = qso.upload_id
        group by callsign, rdas.rda, bands.band) as l0
        group by callsign, rda) as l1
        group by callsign""", None, True)

    for row in data:
        save_json(row['data'],\
            conf.get('web', 'root') + '/json/hunters/' + row['callsign'] + '.json')

def main():
    """export all when called from shell"""
    start_logging('export')
    logging.debug('start export')
    conf = site_conf()
    asyncio.get_event_loop().run_until_complete(export_rankings(conf))
    asyncio.get_event_loop().run_until_complete(export_hunters(conf))

if __name__ == "__main__":
    main()

