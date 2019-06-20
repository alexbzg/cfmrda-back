#!/usr/bin/python3
#coding=utf-8
"""script for sending cfm requests to activators"""
import asyncio
import logging
import base64
from datetime import datetime

from common import site_conf, start_logging
from db import DBConn, exec_cur, splice_params
from ham_radio import load_adif
from ext_logger import ExtLogger

@asyncio.coroutine
def main():
    """sends cfm requests"""
    start_logging('loggers')
    logging.debug('start loading loggers')
    conf = site_conf()
    db_params = conf.items('db')

    _db = DBConn(db_params)
    yield from _db.connect()

    loggers = yield from _db.execute("""
        select callsign, logger, login_data, qso_count, 
            to_char(last_updated, 'YYYY-MM-DD') as last_updated
        from ext_loggers
        where state = 0 and 
            (last_updated is null or last_updated < now() - interval '30 days')
        """, None, True)
    if not loggers:
        logging.debug('No updates are due today.')
        return
    for row in loggers:
        logger = ExtLogger(row['logger'])
        update_params = {}
        adif = None
        try:
            adif = logger.load(row['login_data'], date_from=row['last_updated']).upper()
            logging.debug(row['callsign'] + ' data was downloaded.')
        except Exception:
            logging.exception()
            update_params['state'] = 1
        if adif:

            qso_count = adif.count('<EOR>')
            parsed = load_adif(adif, 'STATION_CALLSIGN')
            date_start, date_end = None, None
            sql_rda = """
                select rda 
                from callsigns_rda
                where callsign = %(callsign)s and
                    (dt_start is null or dt_start <= %(tstamp)s) and
                    (dt_stop is null or dt_stop >= %(tstamp)s)
            """
            qsos = []

            with (yield from _db.pool.cursor()) as cur:
                for qso in parsed['qso']:
                    yield from exec_cur(cur, sql_rda, qso)
                    if cur.rowcount == 1:
                        qso['rda'] = (yield from cur.fetchone())[0]
                        qso['callsign'], qso['station_callsign'] = \
                            qso['station_callsign'], qso['callsign']
                        if not date_start or date_start > qso['tstamp']:
                            date_start = qso['tstamp']
                        if not date_end or date_end < qso['tstamp']:
                            date_end = qso['tstamp']
                        qsos.append(qso)

            if qsos:
                logging.debug(str(len(qsos)) + ' qso found.')
                file_hash = yield from _db.check_upload_hash(adif)

                yield from _db.create_upload(\
                    callsign=loggers['callsign'],\
                    upload_type=loggers['logger'],\
                    date_start=date_start,\
                    date_end=date_end,\
                    file_hash=file_hash,\
                    activators=set([]),
                    qsos=qsos)

            logging.debug('qso saved into db.')

            update_params = {\
                'qso_count': row['qso_count'] + qso_count,\
                'state': 0,\
                'last_updated': datetime.now().strftime("%Y-%m-%d")}

        _db.param_update('ext_loggers', splice_params(row, ('logger', 'callsign')),\
            update_params)
        logging.debug('logger data updated')

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())

