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
from ham_radio import load_adif, BANDS_WL
from ext_logger import ExtLogger

async def main(conf):
    """does the job"""
    db_params = dict(conf.items('db'))

    _db = DBConn(db_params)
    await _db.connect()

    reload_interval = conf.get('web', 'elog_reload', fallback='7 days')

    with (await _db.pool.cursor()) as cur:

        await exec_cur(cur, """
            select json_build_object('id', id, 'callsign', callsign, 
                'logger', logger, 'login_data', login_data, 
                'qso_count', qso_count, 'last_updated', to_char(last_updated, 'YYYY-MM-DD'))
            from ext_loggers 
            where state = 0 and 
                (last_updated is null or last_updated < now() - interval %(reload_interval)s)
            """, {'reload_interval': reload_interval})
        loggers = await cur.fetchall()
        if not loggers:
            logging.debug('No updates are due today.')
            return

        async def rda_search(qso):
            await exec_cur(cur, """
                    select json_build_object('rda', rda, 'start', dt_start, 
                        'stop', dt_stop)
                    from callsigns_rda
                    where callsign = %(station_callsign)s and rda <> '***' and 
                        (dt_start is null or dt_start <= %(tstamp)s) and
                        (dt_stop is null or dt_stop >= %(tstamp)s)
                """, qso)
            if cur.rowcount == 1:
                return (await cur.fetchone())[0]['rda']
            elif cur.rowcount == 0:
                return None
            else:
                rda_data = await cur.fetchall()
                await exec_cur(cur, """
                    select disable_autocfm 
                    from callsigns_meta
                    where callsign = %(station_callsign)s
                """, qso)
                if cur.rowcount == 1:
                    disable_autocfm = (await cur.fetchone())[0]
                    if disable_autocfm:
                        return None
                rdas = {'def': [], 'undef': []}
                for rda_row in rda_data:
                    rda_entry = rda_row[0]
                    entry_type = rdas['def'] if rda_entry['start']\
                        or rda_entry['stop']\
                        else rdas['undef']
                    if rda_entry['rda'] not in entry_type:
                        entry_type.append(rda_entry['rda'])
                entry_type = rdas['def'] if rdas['def']\
                    else rdas['undef']
                if len(entry_type) == 1:
                    return entry_type[0]
                else:
                    return None

        async def rda_check(qso):
            await exec_cur(cur, """
                select from qso 
                where callsign = %(callsign)s and rda = %(rda)s and
                    band = %(band)s and mode = %(mode)s
                limit 1""", qso)
            if cur.rowcount:
                logging.debug("RDA already confirmed:")
                logging.debug(qso)
            return cur.rowcount

        for row_data in loggers:
            row = row_data[0]
            logger = ExtLogger(row['logger'])
            update_params = {}

            if row['logger'] != 'HAMLOG':

                await exec_cur(cur, """
                    select json_build_object('id', id, 
                        'station_callsign', station_callsign, 'rda', rda,
                        'tstamp', tstamp)
                    from qso 
                    where upload_id in 
                        (select id 
                        from uploads 
                        where ext_logger_id = %(id)s)""", row)
                prev_qsos = await cur.fetchall()
                for qso_data in prev_qsos:
                    qso = qso_data[0]
                    rda = await rda_search(qso)
                    if rda:
                        if rda != qso['rda']:
                            qso['rda'] = rda
                            await exec_cur(cur, """
                                update qso
                                set rda = %(rda)s
                                where id = %(id)s
                                """, qso)
                    else:
                        await exec_cur(cur, """
                            delete from qso
                            where id = %(id)s""", qso)

            logger_data = None
            try:
                logger_data = logger.load(row['login_data'])
                logging.info(row['callsign'] + ' ' + row['logger'] + ' data was downloaded.')
            except Exception:
                logging.exception(row['callsign'] + ' ' + row['logger'] + ' error occured')
                update_params['state'] = 1

            if logger_data:

                if row['logger'] == 'HAMLOG':
                    await exec_cur(cur, """
                        delete from qso
                        where upload_id in 
                            (select id 
                            from uploads 
                            where ext_logger_id = %(id)s)""", row)
                    await exec_cur(cur, """
                        delete from uploads
                        where ext_logger_id = %(id)s""", row)

                qso_count = 0
                station_callsign_field = None if row['logger'] == 'eQSL'\
                    else 'STATION_CALLSIGN'
                qsos = []
                date_start, date_end = None, None

                try:

                    if row['logger'] == 'HAMLOG':

                        for entry in logger_data:
                            if entry['band'] in BANDS_WL:
                                qso = {'callsign': entry['mycall'],\
                                    'station_callsign': entry['hiscall'],\
                                    'rda': entry['rda'],\
                                    'band': BANDS_WL[entry['band']],\
                                    'mode': 'SSB' if entry['mainmode'] == 'PH' else entry['mainmode'],\
                                    'tstamp': entry['date']}
                                if not (await rda_check(qso)):
                                    qsos.append(qso)
                                    if not date_start or date_start > qso['tstamp']:
                                        date_start = qso['tstamp']
                                    if not date_end or date_end < qso['tstamp']:
                                        date_end = qso['tstamp']

                        qso_count = len(logger_data)

                    else:

                        for adif in logger_data:

                            adif = adif.upper()
                            qso_count += adif.count('<EOR>')
                            parsed = load_adif(adif, station_callsign_field, ignore_activator=True,\
                                strip_callsign_flag=False)

                            for qso in parsed['qso']:

                                callsign = row['login_data']['Callsign'].upper()\
                                    if row['logger'] == 'eQSL'\
                                    else qso['station_callsign']
                                qso['callsign'], qso['station_callsign'] = \
                                    callsign, qso['callsign']

                                rda = await rda_search(qso)
                                if rda:
                                    qso['rda'] = rda
                                else:
                                    continue

                                if not (await rda_check(qso)):
                                    if not date_start or date_start > qso['tstamp']:
                                        date_start = qso['tstamp']
                                    if not date_end or date_end < qso['tstamp']:
                                        date_end = qso['tstamp']

                                    qsos.append(qso)

                except Exception:
                    logging.exception('Error parsing elog data')
                logging.info(str(qso_count) + ' qsos were downloaded.')
  
                if qsos:
                    logging.info(str(len(qsos)) + ' new rda qso found.')
                    #file_hash = await _db.check_upload_hash(adif.encode('utf-8'))

                    db_res = await _db.create_upload(\
                        callsign=row['callsign'],\
                        upload_type=row['logger'],\
                        date_start=date_start,\
                        date_end=date_end,\
                        file_hash='-',\
                        activators=set([]),
                        ext_logger_id=row['id'],
                        qsos=qsos)

                    logging.debug(str(db_res['qso']['ok']) + ' qso were stored in db.')

                update_params = {\
                    'qso_count': qso_count,\
                    'state': 0,\
                    'last_updated': datetime.now().strftime("%Y-%m-%d")}

                await _db.param_update('ext_loggers', splice_params(row, ('id',)),\
                    update_params)
                logging.debug('logger data updated')

if __name__ == "__main__":
    CONF = site_conf()

    start_logging('loggers', level=CONF.get('logs', 'loggers_level'))
    logging.debug('start loading loggers')

    PID_FILENAME = CONF.get('files', 'loggers_pid')
    PID_FILE = open(PID_FILENAME, 'w')
    try:
        fcntl.lockf(PID_FILE, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        logging.error('another instance is running')
        sys.exit(0)

    asyncio.get_event_loop().run_until_complete(main(CONF))
