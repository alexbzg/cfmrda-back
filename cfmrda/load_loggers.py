#!/usr/bin/python3
#coding=utf-8
"""script for downloading web loggers data and storing it into db"""
import asyncio
import logging
from datetime import datetime
import fcntl
import sys

from common import site_conf, start_logging
from db import DBConn, exec_cur, splice_params
from ham_radio import load_adif
from ext_logger import ExtLogger

@asyncio.coroutine
def main(conf):
    """does the job"""
    db_params = conf.items('db')

    _db = DBConn(db_params)
    yield from _db.connect()

    loggers = yield from _db.execute("""
        select id, callsign, logger, login_data, qso_count, 
            to_char(last_updated, 'YYYY-MM-DD') as last_updated
        from ext_loggers
        where state = 0 and 
            (last_updated is null or last_updated < now() - interval '14 days')
        """, None, True)
    if not loggers:
        logging.debug('No updates are due today.')
        return
    for row in loggers:
        logger = ExtLogger(row['logger'])
        update_params = {}
        adifs = None
        try:
            adifs = logger.load(row['login_data'])
            logging.debug(row['callsign'] + ' ' + row['logger'] + ' data was downloaded.')
        except Exception:
            logging.exception(row['callsign'] + ' ' + row['logger'] + ' error occured')
            update_params['state'] = 1

        if adifs:

            prev_uploads = yield from _db.execute("""
                select id from uploads where ext_logger_id = %(id)s""", row)
            if prev_uploads:
                for upload_id in prev_uploads:
                    yield from _db.remove_upload(upload_id)

            qso_count = 0

            for adif in adifs:
                adif = adif.upper()
                qso_count += adif.count('<EOR>')
                parsed = load_adif(adif, 'STATION_CALLSIGN', ignore_activator=True,\
                    strip_callsign_flag=False)
                date_start, date_end = None, None
                sql_rda = """
                    select distinct rda 
                    from callsigns_rda
                    where callsign = %(callsign)s and rda <> '***' and 
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
                    logging.debug(str(len(qsos)) + ' rda qso found.')
                    file_hash = yield from _db.check_upload_hash(adif.encode('utf-8'))

                    db_res = yield from _db.create_upload(\
                        callsign=row['callsign'],\
                        upload_type=row['logger'],\
                        date_start=date_start,\
                        date_end=date_end,\
                        file_hash=file_hash,\
                        activators=set([]),
                        qsos=qsos)

                    logging.debug(str(db_res['qso']['ok']) + ' qso were stored in db.')

            update_params = {\
                'qso_count': qso_count,\
                'state': 0,\
                'last_updated': datetime.now().strftime("%Y-%m-%d")}

        yield from _db.param_update('ext_loggers', splice_params(row, ('id')),\
            update_params)
        logging.debug('logger data updated')

if __name__ == "__main__":
    start_logging('loggers')
    logging.debug('start loading loggers')
    CONF = site_conf()

    PID_FILENAME = CONF.get('files', 'loggers_pid')
    PID_FILE = open(PID_FILENAME, 'w')
    try:
        fcntl.lockf(PID_FILE, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        logging.error('another instance is running')
        sys.exit(0)

    asyncio.get_event_loop().run_until_complete(main(CONF))

