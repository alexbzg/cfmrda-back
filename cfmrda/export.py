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
    """export rankings data from db to json file for web"""
    logging.debug('export rankings')

    _db = DBConn(conf.items('db'))
    yield from _db.connect()

    rankings = {'hunters': {'total': {}, 'modes': {}},\
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

    rankings['activators']['modes'] = (yield from _db.execute("""
        with bands_data as

                (select activator, count(rda) as rda_count, band, mode,
                    rank() over (partition by mode, band order by count(rda) desc)
                from
                    (select activator, rda, mode, band, count(distinct callsign)
                    from qso
                    group by activator, rda, mode, band
                    having count(distinct callsign) > 99) as rda_cfm
                group by activator, mode, band)

        select json_object_agg(mode,
            json_build_object('bands', bands, 'bandsSum', bands_sum, 'total', total)) as data
        from
            (select mode, bands,
            
                (select json_agg(
                    json_build_object('callsign', activator, 'count', count,
                        'rank', rank))
                from
                    (select activator, sum(rda_count) as count,
                        rank() over(order by sum(rda_count) desc)
                    from bands_data as bd_1
                    where bd_1.mode = l_1.mode
                    group by activator) as l_0_0
                ) as bands_sum,

            (select json_agg(json_build_object('callsign', callsign, 
                'count', count, 'rank', rank)) as data
            from 
                (select activator as callsign, count(*),
                    rank() over (order by count(*) desc)
                from 
                    (select activator, rda, count(distinct callsign)
                    from qso
                    where qso.mode = l_1.mode
                    group by activator, rda
                    having count(distinct callsign) > 99) as rda_filter
                group by activator) as l_0
            ) as total
                    
            from
            (select mode, json_object_agg(band, data) as bands
            from
                (select mode, band, json_agg(json_build_object(
                    'callsign', activator, 'count', rda_count,
                    'rank', rank)) as data
                from bands_data
                group by mode, band) l_0
            group by mode) as l_1) as l_2
        
        """))['data']

    activators_bands = yield from _db.execute("""
        with bands_data as 

        (select activator, count(rda) as rda_count, band, 
            rank() over (partition by band order by count(rda) desc)
        from 
            (select activator, rda, band, count(distinct callsign)
            from qso
            group by activator, rda, band
            having count(distinct callsign) > 99) as rda_filter
        group by activator, band)

        select 
            (select json_object_agg(band, data) 
            from
                (select band, 
                    json_agg(json_build_object('callsign', activator, 
                        'rank', rank, 'count', rda_count)) as data 
                from bands_data 
                group by band) as l_0) as bands,
            (select json_agg(json_build_object('callsign', activator, 'rank', rank,
                'count', rda_count))
            from
                (select activator, sum(rda_count) as rda_count,
                    rank() over (order by sum(rda_count) desc) 
                from bands_data
                group by activator limit 100) as l0_1) as bands_sum
        """)
    rankings['activators']['total']['bands'] = activators_bands['bands']
    rankings['activators']['total']['bandsSum'] = activators_bands['bands_sum']

    rankings['hunters']['total']['total'] = yield from _db.execute("""
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

    rankings['hunters']['modes'] = (yield from _db.execute("""
        with bands_data as 
        (select callsign, mode, band, count(distinct rda),
            rank() over (partition by mode, band order by count(distinct rda) desc)
        from
            (select callsign, mode, band, rda 
            from qso
            union all
            (select activator as callsign, mode, band, rda
            from qso
            group by activator, rda, mode, band
            having count(distinct callsign) > 99)) as rda_all
        group by callsign, mode, band)

        select json_object_agg(mode, 
            json_build_object('total', total, 'bands', bands, 
            'bandsSum', bands_sum)) as data
        from
            (select mode, 
                json_object_agg(band, data) as bands,

                (select json_agg(json_build_object('callsign', callsign, 'rank', rank, 
                    'count', count)) 
                from
                    (select callsign, rank() over (order by count(distinct rda) desc),
                        count(distinct rda) 
                    from
                        (select callsign, rda 
                        from qso
                        where qso.mode=l_0.mode
                        union all
                        select activator as callsign, rda
                        from qso
                        where qso.mode=l_0.mode
                        group by activator, rda
                        having count(distinct callsign) > 99) as rda_all
                    group by callsign) as total) as total,

                (select json_agg(json_build_object('callsign', callsign, 'rank', rank, 
                    'count', count)) 
                from
                    (select callsign, sum(count) as count, 
                        rank() over (order by sum(count) desc)
                    from bands_data as bd_bands_sum
                    where bd_bands_sum.mode = l_0.mode
                    group by callsign) as bands_sum) as bands_sum

            from
                (select mode, band, json_agg(json_build_object('callsign', callsign, 
                    'rank', rank, 'count', count)) as data 
                from bands_data 
                group by mode, band) as l_0
            group by mode) as l_1
        """))['data']

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
    rankings['hunters']['total']['bands'] = hunters_bands['bands']
    rankings['hunters']['total']['bandsSum'] = hunters_bands['bands_sum']

    save_json(rankings, conf.get('web', 'root') + '/json/rankings.json')

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
        if not os.getuid():
            shutil.chown(conf.get('web', 'root') + '/json/rankings.json',\
                user=conf.get('web', 'user'), group=conf.get('web', 'group'))

if __name__ == "__main__":
    main()

