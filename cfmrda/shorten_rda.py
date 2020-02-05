#!/usr/bin/python3
#coding=utf-8

from json_utils import load_json, save_json


awards = load_json('/var/www/adxc.73/awardsValues.json')
rda = [x for x in awards if x['name'] == 'RDA'][0]

short= []
full =[]

for group in rda['groups'].keys():
    new_group = {'group': group}
    values = [x for x in rda['values'] if x['group'] == group]
    last_value = int(values[-1]['displayValue'])
    if last_value != len(values):
        skip = []
        c_el = 1
        c_no = 1
        while c_no < last_value:
            if int(values[c_el - 1]['displayValue']) != c_no:
                skip.append(c_no)
            else:
                c_el += 1
            c_no += 1
        new_group['skip'] = skip
    new_group['last'] = last_value
    short.append(new_group)
    for val in values:
        full.append(group + '-' + val['displayValue'])

short.sort(key=lambda group: group['group'])
full.sort()
save_json(short, '/var/www/cfmrda-dev/src/rdaShort.json')
save_json(full, '/var/www/cfmrda-dev/public/json/rdaValues.json')

