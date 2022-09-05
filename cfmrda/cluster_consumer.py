#!/usr/bin/python3
#coding=utf-8

from pymongo import MongoClient

def get_data(db_params, all_data=False, spot_filter=None):
    MC = MongoClient(db_params['host'],
        username=db_params['user'],
        password=db_params['password'],
        authSource='admin')

    DB = MC.dx
    if not spot_filter:
        spot_filter = {}
    if not all_data:
        ts_prev = DB.consumers.find_one({'id':db_params['consumer']})['last']
        if ts_prev:
            spot_filter['ts'] = {'$gt': ts_prev}

    data = list(DB.dx.find(spot_filter).sort('ts', -1))
    if data:
        DB.consumers.update_one({'id': db_params['consumer']}, {'$set': {'last': data[0]['ts']}})

    return data
