#!/usr/bin/python3
#coding=utf-8
"""creates json file for getting rda title by value"""

import re

import requests

from json_utils import save_json

rda_rus_rsp = requests.get('http://rdaward.org/rda_rus.txt')
rda_rus_rsp.encoding = 'cp1251'
lines = rda_rus_rsp.text.split('\r\n')

rda_titles = {}

re_rda_line = re.compile(r'(^[A-Z][A-Z]-\d\d)\s+([^\t]+)\t*((?:\*\*\*)?[A-Z][A-Z]-\d\d|\*\*\*)?')
for line in lines:
    match_rda_line = re_rda_line.match(line)
    if match_rda_line:
        rda_titles[match_rda_line.group(1)] = match_rda_line.group(2)

save_json(rda_titles, '/var/www/cfmrda-dev/public/json/rda_titles.json')

