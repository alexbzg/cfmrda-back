#!/usr/bin/python3
#coding=utf-8
"""updates db blacklist and deletes new blacklisted qsos"""
import asyncio
import logging
from common import site_conf, start_logging
from db import DBConn
from json_utils import load_json

CONF = site_conf()

async def update_blacklist():
    logging.debug('update stations blacklist start')

    db_params = dict(CONF.items('db'))
    _db = DBConn(db_params)
    await _db.connect()

    def build_set(seq):
        return set((item['callsign'], item['date_begin'], item['date_end']) for item in seq)

    def to_dict(bl_tuple):
        return {'callsign': bl_tuple[0], 'date_begin': bl_tuple[1], 'date_end': bl_tuple[2]}

    bl_json_path = CONF.get('web', 'root') + '/json/stations_blacklist.json'
    bl_json = build_set(load_json(bl_json_path) or [])
    db_data = (await
            _db.execute('select callsign, date_begin::text, date_end::text from stations_blacklist')) or []
    if isinstance(db_data, dict):
        db_data = [db_data]
    bl_db = build_set(db_data)

    for entry in bl_json - bl_db:
        bl_dict = to_dict(entry)
        await _db.execute("""insert into stations_blacklist (callsign, date_begin, date_end)
                                values (%(callsign)s, %(date_begin)s, %(date_end)s)""", bl_dict)
        await _db.execute("""
                            delete from qso
                            where station_callsign = %(callsign)s and
                                (%(date_begin)s is null or tstamp >= %(date_begin)s) and
                                (%(date_end)s is null or tstamp <= %(date_end)s)""", bl_dict)

    for entry in bl_db - bl_json:
        await _db.execute("""delete from stations_blacklist
                            where callsign = %(callsign)s and
                                date_begin is not distinct from %(date_begin)s and 
                                date_end is not distinct from %(date_end)s""",
                            to_dict(entry))

    await _db.disconnect()

def main():
    start_logging('stations_blacklist')

    asyncio.get_event_loop().run_until_complete(update_blacklist())


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logging.exception('Stations blacklist update exception')
