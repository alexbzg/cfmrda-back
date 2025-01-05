#!/usr/bin/python3
#coding=utf-8
"""creates json file for getting rda title by value"""

import re

import requests

from json_utils import save_json

rda_rus_rsp = requests.get('https://rdaward.ru/share/RDA_list_2025.csv')
rda_rus_rsp.encoding = 'cp1251'
lines = rda_rus_rsp.text.split('\r\n')[1:]

rda_titles = {}
rda_list_short = []
rda_list_full = []

for line in lines:
    if line.count(';') == 2:
        value, _, title = line.split(';')
        rda_titles[value] = title

        rda_list_full.append(value)

        group = value[:2]
        if not rda_list_short or rda_list_short[-1]['group'] != group:
            rda_list_short.append({'group': group, 'last': 0})
        int_val = int(value[3:])
        if rda_list_short[-1]['last'] + 1 < int_val:
            rda_list_short[-1].setdefault('skip', [])
            rda_list_short[-1]['skip'].extend(
                list(range(rda_list_short[-1]['last'] + 1, int_val))
                )
        rda_list_short[-1]['last'] = int_val


save_json(rda_titles, '/var/www/cfmrda-dev/public/json/rda_titles.json')
save_json(rda_list_short, '/var/www/cfmrda-dev/src/rdaShort.json')
save_json(rda_list_full, '/var/www/cfmrda-dev/public/json/rdaValues.json')

