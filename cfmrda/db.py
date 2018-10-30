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

