#!/usr/bin/python3
#coding=utf-8

from json_utils import load_json, save_json

rda = load_json('/var/www/cfmrda-dev/public/json/rda.json')

new = []

for group in rda:
    new_group = {'group': group['group']}
    last_value = int(group['values'][-1]['displayValue'])
    if last_value != len(group['values']):
        skip = []
        c_el = 1
        c_no = 1
        while c_no < last_value:
            if int(group['values'][c_el - 1]['displayValue']) != c_no:
                skip.append(c_no)
            else:
                c_el += 1
            c_no += 1
        new_group['skip'] = skip
    new_group['last'] = last_value
    new.append(new_group)

save_json(new, '/var/www/cfmrda-dev/src/rdaShort.json')


