#!/usr/bin/python3
#coding=utf-8

import logging
import json
import asyncio

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


class DBConn:

    def __init__(self, db_params):
        self.dsn = ' '.join([k + "='" + v + "'" for k, v in db_params])
        self.verbose = False
        self.pool = None
        self.error = None

    @asyncio.coroutine
    def connect(self):
        try:
            self.pool = yield from aiopg.create_pool(self.dsn, \
                    timeout=600,
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
                " where " + params_str(id_params, ' and '), \
                id_params))

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
                if params:
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
    def insert_upload(self, callsign=None, date_start=None, date_end=None,\
        file_hash=None, upload_type='adif', activators=None):
        upl_id = yield from self.execute("""
            insert into uploads
                (user_cs, date_start, date_end, hash,
                upload_type)
            values (%(callsign)s, 
                %(date_start)s, %(date_end)s, %(hash)s,
                %(upload_type)s)
            returning id""",\
            {'callsign': callsign,\
            'date_start': date_start,\
            'date_end': date_end,\
            'hash': file_hash,\
            'upload_type': upload_type})
        if not upl_id:
            raise Exception()

        act_sql = """insert into activators
            values (%(upload_id)s, %(activator)s)"""
        act_params = [{'upload_id': upl_id,\
            'activator': act} for act in activators]
        res = yield from self.execute(act_sql, act_params)
        if not res:
            raise Exception()
        return upl_id


