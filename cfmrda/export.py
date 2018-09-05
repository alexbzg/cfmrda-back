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

    rankings['activators']['total'] = yield from _db.execute("""
select activator, count(*), rank() over (order by count(*) desc) from
(select strip_callsign(station_callsign) as activator, rda, count(distinct callsign) from qso
group by strip_callsign(station_callsign), rda
having count(distinct callsign) > 100) as rda_filter
group by activator
limit 100        
            """, None, True)

    for band in BANDS:

        rankings['activators']['bands'][band] = yield from _db.execute("""
            select callsign, count(*), rank() over (order by count(*) desc) 
            from
                (select callsign, rda, sum(qso_count) 
                from stats_activators 
                where band = %(band)s 
                group by callsign, rda 
                having sum(qso_count) > 100) as rda_filter
            group by callsign""", {'band': band}, True)

        rankings['hunters']['bands'][band] = yield from _db.execute("""
            select callsign, count(*), rank() over (order by count(*) desc) 
            from stats_hunters 
            where band = %(band)s 
            group by callsign""", {'band': band}, True)

    rankings['activators']['bandsSum'] = yield from _db.execute("""
        select callsign, count(*), rank() over (order by count(*) desc) 
        from 
            (select callsign, rda, band, sum(qso_count) 
            from stats_activators 
            group by callsign, rda, band 
            having sum(qso_count) > 100) as rda_filter
        group by callsign""", None, True)

    rankings['hunters']['total'] = yield from _db.execute("""
        select callsign, count(*), rank() over (order by count(*) desc) 
        from 
            (select distinct callsign, rda 
            from stats_hunters) as rda_filter
        group by callsign""", None, True)

    rankings['hunters']['bandsSum'] = yield from _db.execute("""
        select callsign, count(*), rank() over (order by count(*) desc) 
        from stats_hunters group by callsign""", None, True)

    save_json(rankings, conf.get('web', 'root') + '/json/rankings.json')

def export_hunters():
    """export rankings data from db to json file for web -
    not implemented yet"""
    pass

def main():
    """export all when called from shell"""
    start_logging('export')
    logging.debug('start export')
    conf = site_conf()
    asyncio.get_event_loop().run_until_complete(export_rankings(conf))
    export_hunters()

if __name__ == "__main__":
    main()

