#!/usr/bin/python3
#coding=utf-8
"""functions for exporting stats data from db to frontend json files"""
import argparse

from common import site_conf, start_logging
from json_utils import load_json, save_json
import cluster_consumer

argparser = argparse.ArgumentParser(usage="-c clears previous data -a consumes all data")
argparser.add_argument('-c', action='store_true')
argparser.add_argument('-a', action='store_true')
args = argparser.parse_args()

conf = site_conf()
start_logging('cluster')
list_length = conf.getint('cluster', 'list_length')

dx_data = cluster_consumer.get_data('cfmrda', dict(conf['cluster_db']), all_data=args.a,
        spot_filter={'rda': {'$nin': [None, '?']}})

rda_dx_fname = conf.get('web', 'root') + '/json/dx.json'
rda_dx = []
if not args.c:
    rda_dx = load_json(rda_dx_fname)
    if not rda_dx:
        rda_dx = []
idx = 0

with open(conf.get('files', 'cluster'), 'r') as fdx:
    for item in dx_data:
        del item['_id']
        rda_dx = [x for x in rda_dx if x['ts'] <=  item['ts'] - 5400
            or x['cs'] != item['cs'] or not -1 < x['freq'] - item['freq'] < 1]

        rda_dx.insert(idx, item)
        idx += 1
    if idx > 0:
        if len(rda_dx) > list_length:
            rda_dx = rda_dx[:list_length]
        save_json(rda_dx, rda_dx_fname)
