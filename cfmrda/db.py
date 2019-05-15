#!/usr/bin/python3
#coding=utf-8

import logging
import json
import asyncio
import hashlib

import aiopg
from psycopg2.extensions import TRANSACTION_STATUS_IDLE

@asyncio.coroutine
def to_dict(cur, keys=None):
    if cur and cur.rowcount:
        columns_names = [col.name for col in cur.description]
        if cur.rowcount == 1 and not keys:
            data = yield from cur.fetchone()
            if len(columns_names) == 1:
                return data[0]
            else:
                return dict(zip(columns_names, data))
        else:
            data = yield from cur.fetchall()
            if ('id' in columns_names) and keys:
                id_idx = columns_names.index('id')
                return {row[id_idx]: dict(zip(columns_names, row)) \
                        for row in data}
            else:
                if len(columns_names) == 1:
                    return [row[0] for row in data]
                else:
                    return [dict(zip(columns_names, row)) for\
                        row in data]
    else:
        return False

def typed_values_list(_list, _type=None):
    """convert list to values string, skips values not of specified type if
    type is specified"""
    return '(' + ', '.join((str(x) for x in _list\
        if not _type or isinstance(x, _type))) + ')'

def params_str(params, str_delim):
    return str_delim.join([x + " = %(" + x + ")s" for x in params.keys()])

def splice_params(data, params):
    return {param: json.dumps(data[param]) \
            if isinstance(data[param], dict) else data[param] \
        for param in params \
        if param in data}

@asyncio.coroutine
def init_connection(conn):
    conn.set_client_encoding('UTF8')
    logging.debug('new db connection')

@asyncio.coroutine
def exec_cur(cur, sql, params=None):
    try:
        yield from cur.execute(sql, params)
        return True
    except Exception:
        logging.exception("Error executing: " + sql + "\n",\
            exc_info=True)
        if params:
            logging.error("Params: ")
            logging.error(params)
        return False

class DBConn:

    def __init__(self, db_params, verbose=False):
        self.dsn = ' '.join([k + "='" + v + "'" for k, v in db_params])
        self.verbose = verbose
        self.pool = None
        self.error = None

    @asyncio.coroutine
    def connect(self):
        try:
            self.pool = yield from aiopg.create_pool(self.dsn, \
                    timeout=18000,\
                    on_connect=init_connection)
            logging.debug('db connections pool created')
        except Exception:
            logging.exception('Error creating connection pool')
            logging.error(self.dsn)

    @asyncio.coroutine
    def fetch(self, sql, params=None):
        res = False
        cur = yield from self.execute(sql, params)
        if cur.rowcount:
            res = yield from cur.fetchall()
        return res

    @asyncio.coroutine
    def param_update(self, table, id_params, upd_params):
        return (yield from self.execute('update ' + table + \
                ' set ' + params_str(upd_params, ', ') + \
                " where " + params_str(id_params, ' and '), \
                dict(id_params, **upd_params)))

    @asyncio.coroutine
    def param_delete(self, table, id_params):
        return (yield from self.execute('delete from ' + table + \
                " where " + params_str(id_params, ' and ') +\
                " returning *", id_params))

    @asyncio.coroutine
    def param_update_insert(self, table, id_params, upd_params):
        lookup = yield from self.get_object(table, id_params, False, True)
        res = None
        if lookup:
            res = yield from self.param_update(table, id_params, upd_params)
        else:
            res = yield from self.get_object(table, dict(id_params, **upd_params),\
                    True)
        return res

    @asyncio.coroutine
    def execute(self, sql, params=None, keys=None):
        res = False
        with (yield from self.pool.cursor()) as cur:
            try:
                if self.verbose:
                    logging.debug(sql)
                    logging.debug(params)
                if not params or isinstance(params, dict):
                    yield from cur.execute(sql, params)
                    res = (yield from to_dict(cur, keys))\
                        if cur.description != None else True
                else:
                    yield from cur.execute('begin transaction;')
                    for item in params:
                        yield from cur.execute(sql, item)
                    yield from cur.execute('commit transaction;')
                    res = True
            except Exception:
                if cur.connection.get_transaction_status() !=\
                        TRANSACTION_STATUS_IDLE:
                    yield from cur.execute('rollback transaction;')
                logging.exception("Error executing: " + sql + "\n",\
                    exc_info=True)
                if params and not isinstance(params, dict):
                    logging.error("Params: ")
                    logging.error(params)
        return res


    @asyncio.coroutine
    def get_object(self, table, params, create=False, never_create=False):
        sql = ''
        res = False
        if not create:
            sql = "select * from %s where %s" %\
                (table,\
                " and ".join([k + " = %(" + k + ")s"\
                    if params[k] != None\
                    else k + " is null"\
                    for k in params.keys()]))
            res = yield from self.execute(sql, params)
        if create or (not res and not never_create):
            keys = params.keys()
            sql = "insert into " + table + " (" + \
                ", ".join(keys) + ") values (" + \
                ', '.join(["%(" + k + ")s" for k in keys]) + \
                ") returning *"
            logging.debug('creating object in db')
            res = yield from self.execute(sql, params)
        return res

    @asyncio.coroutine
    def check_upload_hash(self, hash_data):
        file_hash = hashlib.md5(hash_data).hexdigest()
        hash_check = yield from self.execute("""
            select id from uploads where hash = %(hash)s
            """, {'hash': file_hash})
        logging.debug(hash_check)
        if hash_check:
            logging.error("Duplicate adif id: "  + str(hash_check))
            return False
        return file_hash

    @asyncio.coroutine
    def create_upload(self, callsign=None, date_start=None, date_end=None,\
        file_hash=None, upload_type='adif', activators=None, qsos=None):

        res = {'message': 'Ошибка загрузки',
               'qso': {\
                    'ok': 0,\
                    'error': 0\
               }
              }

        logging.debug('create upload start')

        with (yield from self.pool.cursor()) as cur:
            try:
                yield from exec_cur(cur, 'begin transaction')
                logging.debug('transaction start')

                upl_params = {'callsign': callsign,\
                    'date_start': date_start,\
                    'date_end': date_end,\
                    'hash': file_hash,\
                    'upload_type': upload_type}

                upl_res = yield from exec_cur(cur, """
                    insert into uploads
                        (user_cs, date_start, date_end, hash,
                        upload_type)
                    values (%(callsign)s, 
                        %(date_start)s, %(date_end)s, %(hash)s,
                        %(upload_type)s)
                    returning id""", upl_params)
                if not upl_res or not cur.rowcount:
                    logging.error('upload create failed! Params:')
                    logging.error(upl_params)
                    raise Exception()
                upl_id = (yield from cur.fetchone())[0]
                if not upl_id:
                    logging.error('upload create failed! Params:')
                    logging.error(upl_params)
                    raise Exception()
                logging.debug('upload created')

                act_sql = """insert into activators
                    values (%(upload_id)s, %(activator)s)"""
                for act in activators:
                    act_params = {'upload_id': upl_id, 'activator': act} 
                    if not (yield from exec_cur(cur, act_sql, act_params)):
                        logging.error('activators create failed! Params:')
                        logging.error(act_params)
                        raise Exception()
                logging.debug('activators created')

                qso_sql = """insert into qso
                    (upload_id, callsign, station_callsign, rda,
                        band, mode, tstamp)
                    values (%(upload_id)s, %(callsign)s,
                        %(station_callsign)s, %(rda)s, %(band)s,
                        %(mode)s, %(tstamp)s)
                    returning id"""
                for qso in qsos:
                    qso['upload_id'] = upl_id
                    qso_res = yield from exec_cur(cur, qso_sql, qso)
                    qso_id = None
                    if qso_res and cur.rowcount:
                        qso_id = (yield from cur.fetchone())[0]
                    res['qso']['ok' if qso_id else 'error'] += 1

                if res['qso']['ok']:
                    res['message'] = 'OK'
                else:
                    res['message'] = 'Не найдено корректных qso.'
                    raise Exception()

                yield from exec_cur(cur, 'commit transaction')

            except Exception:
                logging.exception('create upload failed')
                if cur.connection.get_transaction_status() !=\
                        TRANSACTION_STATUS_IDLE:
                    yield from exec_cur(cur, 'rollback transaction;')

            return res

    @asyncio.coroutine
    def get_old_callsigns(self, callsign, confirmed=False):
        """returns array of old callsigns"""
        sql = """select array_agg(old)
            from old_callsigns
            where new = %(callsign)s"""
        if confirmed:
            sql += " and confirmed"
        return (yield from self.execute(sql, {'callsign': callsign}))

    @asyncio.coroutine
    def get_new_callsign(self, callsign):
        """returns new callsign or False"""
        return (yield from self.execute("""
            select new 
            from old_callsigns
            where confirmed and old = %(callsign)s
            """, {'callsign': callsign}))

    @asyncio.coroutine
    def set_old_callsigns(self, callsign, new_old, confirm=False):
        """changes old callsigns of the callsign returns False on db error,
        'OK' or warnings string"""
        new_check = yield from self.get_new_callsign(callsign)
        if new_check:
            return "Позывной " + callsign + " назначен старым позывным для "\
                + new_check + " и не может иметь старых позывных."
        current_old = yield from self.get_old_callsigns(callsign)
        if not current_old:
            current_old = []
        current_confirmed = [] if confirm else\
            (yield from self.get_old_callsigns(callsign, True))
        if not current_confirmed:
            current_confirmed = []
        msg = ''
        add = []
        delete = [{'old': cs, 'new': callsign} for cs in current_old\
                if cs not in new_old and (cs not in current_confirmed or confirm)]
        to_confirm = []
        for _cs in new_old:
            check = yield from self.execute("""select new
                from old_callsigns 
                where confirmed and old = %(cs)s and new <> %(new)s""",\
                {'cs': _cs, 'new': callsign})
            if check:
                msg += ('\n' if msg else '') +\
                    "Позывной " + _cs + " уже назначен старым позывным " +\
                    check + "."
            else:
                if _cs in current_old and confirm:
                    to_confirm.append({'old': _cs, 'new': callsign, 'confirmed': confirm})
                if _cs not in current_old:
                    add.append({'old': _cs, 'new': callsign, 'confirmed': confirm})
        if add:
            if not (yield from self.execute("""
                insert into old_callsigns (old, new, confirmed)
                values (%(old)s, %(new)s, %(confirmed)s)""", add)):
                return False
        if delete:
            if not (yield from self.execute("""
                delete from old_callsigns
                where old = %(old)s and new = %(new)s""", delete)):
                return False
        if to_confirm:
            if not (yield from self.execute("""
                update old_callsigns
                set confirmed = true
                where old =%(old)s and new = %(new)s""", to_confirm)):
                return False
        return msg if msg else 'OK'

    @asyncio.coroutine
    def cfm_blacklist(self, callsign):
        """adds callsign to blacklist fro cfm requests"""
        return (yield from self.execute("""
            insert into cfm_request_blacklist
            values (%(callsign)s)""",\
            {'callsign': callsign}, False))
