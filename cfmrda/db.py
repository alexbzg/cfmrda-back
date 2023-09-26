#!/usr/bin/python3
#coding=utf-8

import logging
import json
import asyncio
import hashlib

import aiopg
import psycopg2
from psycopg2.extensions import TRANSACTION_STATUS_IDLE

class CfmrdaDbException(Exception):

    def __init__(self, message):
        msg_trim = message.splitlines()[0].split('cfmrda_db_error:')[1]
        super().__init__(msg_trim)

async def to_dict(cur, keys=None):
    if cur and cur.rowcount:
        columns_names = [col.name for col in cur.description]
        if cur.rowcount == 1 and not keys:
            data = await cur.fetchone()
            if len(columns_names) == 1:
                return data[0]
            else:
                return dict(zip(columns_names, data))
        else:
            data = await cur.fetchall()
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

async def init_connection(conn):
    await conn.set_client_encoding('UTF8')
    logging.debug('new db connection')

async def exec_cur(cur, sql, params=None):
    try:
        await cur.execute(sql, params)
        return True
    except Exception as exc:
        trap_db_exception(exc, sql, params)
        return False

def trap_db_exception(exc, sql, params=None):
    if isinstance(exc, psycopg2.InternalError) or\
        isinstance(exc, psycopg2.DatabaseError):
        logging.debug(exc.pgerror)
        if 'cfmrda_db_error' in exc.pgerror:
            raise CfmrdaDbException(exc.pgerror)
    logging.exception("Error executing: " + sql + "\n",\
        exc_info=True)
    if params and isinstance(params, dict):
        logging.error("Params: ")
        logging.error(params)

class DBConn:

    def __init__(self, db_params, verbose=False):
        self.db_params = db_params.copy()
        self.verbose = verbose
        self.pool = None
        self.error = None

    async def disconnect(self):
        if self.pool:
            self.pool.terminate()
            await self.pool.wait_closed()

    async def connect(self):
        try:
            self.pool = await aiopg.create_pool(timeout=30000, maxsize=3, **self.db_params)
            logging.debug('db connections pool created')
        except Exception:
            logging.exception('Error creating connection pool')
            logging.error(self.db_params)

    async def fetch(self, sql, params=None):
        res = False
        cur = await self.execute(sql, params)
        if cur.rowcount:
            res = await cur.fetchall()
        return res

    async def param_update(self, table, id_params, upd_params):
        return (await self.execute('update ' + table + \
                ' set ' + params_str(upd_params, ', ') + \
                " where " + params_str(id_params, ' and '), \
                dict(id_params, **upd_params)))

    async def param_delete(self, table, id_params):
        return (await self.execute('delete from ' + table + \
                " where " + params_str(id_params, ' and ') +\
                " returning *", id_params))

    async def param_update_insert(self, table, id_params, upd_params):
        lookup = await self.get_object(table, id_params, False, True)
        res = None
        if lookup:
            res = await self.param_update(table, id_params, upd_params)
        else:
            res = await self.get_object(table, dict(id_params, **upd_params),\
                    True)
        return res

    async def execute(self, sql, params=None, keys=None, progress=None):
        res = False
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                try:
                    if self.verbose:
                        logging.debug(sql)
                        logging.debug(params)
                    if not params or isinstance(params, dict):
                        await cur.execute(sql, params)
                        res = await to_dict(cur, keys) if cur.description is not None else True
                    else:
                        await cur.execute('begin transaction;')
                        cnt = 0
                        cnt0 = 0
                        for item in params:
                            cnt0 += 1
                            await cur.execute(sql, item)
                            if cnt0 == 100:
                                cnt += cnt0
                                cnt0 = 0
                                if progress:
                                    logging.debug(str(cnt) + '/' + str(len(params)))
                        await cur.execute('commit transaction;')
                        res = True
                except Exception as exc:
                    if await cur.connection.get_transaction_status() !=\
                            TRANSACTION_STATUS_IDLE:
                        await cur.execute('rollback transaction;')
                    trap_db_exception(exc, sql, params)
        return res


    async def get_object(self, table, params, create=False, never_create=False):
        sql = ''
        res = False
        if not create:
            sql = "select * from %s where %s" %\
                (table,\
                " and ".join([k + " = %(" + k + ")s"\
                    if params[k] != None\
                    else k + " is null"\
                    for k in params.keys()]))
            res = await self.execute(sql, params)
        if create or (not res and not never_create):
            keys = params.keys()
            sql = "insert into " + table + " (" + \
                ", ".join(keys) + ") values (" + \
                ', '.join(["%(" + k + ")s" for k in keys]) + \
                ") returning *"
            logging.debug('creating object in db')
            res = await self.execute(sql, params)
        return res

    async def check_upload_hash(self, hash_data):
        file_hash = hashlib.md5(hash_data).hexdigest()
        return file_hash

    async def create_upload(self, callsign=None, date_start=None, date_end=None,\
        file_hash=None, upload_type='adif', activators=None, qsos=None, ext_logger_id=None):

        res = {'message': 'Ошибка загрузки',\
               'qso': {'ok': 0, 'error': 0, 'errors': {}}
              }

        def append_error(msg):
            if msg not in res['qso']['errors']:
                res['qso']['errors'][msg] = 0
            res['qso']['errors'][msg] += 1
            res['qso']['error'] += 1

        logging.debug('create upload start')

        with (await self.pool.cursor()) as cur:
            try:
                await exec_cur(cur, 'begin transaction')
                logging.debug('transaction start')

                upl_params = {'callsign': callsign,\
                    'date_start': date_start,\
                    'date_end': date_end,\
                    'hash': file_hash,\
                    'upload_type': upload_type,\
                    'ext_logger_id': ext_logger_id}

                upl_res = await exec_cur(cur, """
                    insert into uploads
                        (user_cs, date_start, date_end, hash,
                        upload_type, ext_logger_id)
                    values (%(callsign)s, 
                        %(date_start)s, %(date_end)s, %(hash)s,
                        %(upload_type)s, %(ext_logger_id)s)
                    returning id""", upl_params)
                if not upl_res or not cur.rowcount:
                    logging.error('upload create failed! Params:')
                    logging.error(upl_params)
                    raise Exception()
                upl_id = (await cur.fetchone())[0]
                if not upl_id:
                    logging.error('upload create failed! Params:')
                    logging.error(upl_params)
                    raise Exception()
                logging.debug('upload created')

                act_sql = """insert into activators
                    values (%(upload_id)s, %(activator)s)"""
                for act in activators:
                    act_params = {'upload_id': upl_id, 'activator': act}
                    if not (await exec_cur(cur, act_sql, act_params)):
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
                cfm_sql = """
                    select
                    from qso 
                    where callsign = %(callsign)s and rda = %(rda)s and
                        band = %(band)s and mode = %(mode)s
                    limit 1
                """

                savepoint_fl = False

                async                 def savepoint():
                    nonlocal savepoint_fl
                    if savepoint_fl:
                        await exec_cur(cur, "release savepoint upl_savepoint;")
                    await exec_cur(cur, "savepoint upl_savepoint;")
                    savepoint_fl = True

                async                 def rollback_savepoint():
                    await exec_cur(cur, "rollback to savepoint upl_savepoint;")

                await savepoint()
                for qso in qsos:
                    qso['upload_id'] = upl_id
                    try:
                        if ext_logger_id:
                            cfm_res = await exec_cur(cur, cfm_sql, qso)
                            if cfm_res and cur.rowcount:
                                continue
                        qso_res = await exec_cur(cur, qso_sql, qso)
                        qso_id = None
                        if qso_res and cur.rowcount:
                            qso_id = (await cur.fetchone())[0]
                        if qso_id:
                            res['qso']['ok'] += 1
                            await savepoint()
                        else:
                            append_error('Некорректное QSO (не загружено)')
                            await rollback_savepoint()
                    except CfmrdaDbException as exc:
                        append_error(str(exc))
                        await rollback_savepoint()

                if res['qso']['ok']:
                    res['message'] = 'OK'
                else:
                    res['message'] = 'Не найдено корректных qso.'
                    raise Exception()

                await exec_cur(cur, 'commit transaction')

            except Exception:
                logging.exception('create upload failed')
                if cur.connection.get_transaction_status() !=\
                        TRANSACTION_STATUS_IDLE:
                    await exec_cur(cur, 'rollback transaction;')

            return res

    async def remove_upload(self, _id):
        """removes upload with all qso in it returns True on success else False"""
        if (await self.execute("""delete from qso where upload_id = %(id)s""",\
                {'id': _id})):
            if (await self.execute("""delete from uploads where id = %(id)s""",\
                {'id': _id})):
                return True
        return False

    async def get_old_callsigns(self, callsign, confirmed=False):
        """returns array of old callsigns"""
        sql = """select array_agg(old)
            from old_callsigns
            where new = %(callsign)s"""
        if confirmed:
            sql += " and confirmed"
        return (await self.execute(sql, {'callsign': callsign}))

    async def get_new_callsign(self, callsign):
        """returns new callsign or False"""
        return (await self.execute("""
            select new 
            from old_callsigns
            where confirmed and old = %(callsign)s
            """, {'callsign': callsign}))

    async def set_old_callsigns(self, callsign, new_old, confirm=False):
        """changes old callsigns of the callsign returns False on db error,
        'OK' or warnings string"""
        new_check = await self.get_new_callsign(callsign)
        if new_check:
            return "Позывной " + callsign + " назначен старым позывным для "\
                + new_check + " и не может иметь старых позывных."
        current_old = await self.get_old_callsigns(callsign)
        if not current_old:
            current_old = []
        current_confirmed = [] if confirm else\
            (await self.get_old_callsigns(callsign, True))
        if not current_confirmed:
            current_confirmed = []
        msg = ''
        add = []
        delete = [{'old': cs, 'new': callsign} for cs in current_old\
                if cs not in new_old and (cs not in current_confirmed or confirm)]
        to_confirm = []
        for _cs in new_old:
            check = await self.execute("""select new
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
            if not (await self.execute("""
                insert into old_callsigns (old, new, confirmed)
                values (%(old)s, %(new)s, %(confirmed)s)""", add)):
                return False
        if delete:
            if not (await self.execute("""
                delete from old_callsigns
                where old = %(old)s and new = %(new)s""", delete)):
                return False
        if to_confirm:
            if not (await self.execute("""
                update old_callsigns
                set confirmed = true
                where old =%(old)s and new = %(new)s""", to_confirm)):
                return False
        return msg if msg else 'OK'

    async def cfm_blacklist(self, callsign):
        """adds callsign to blacklist fro cfm requests"""
        return (await self.execute("""
            insert into cfm_request_blacklist
            values (%(callsign)s)""",\
            {'callsign': callsign}, False))
