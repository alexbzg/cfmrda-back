#!/usr/bin/python3
#coding=utf-8

import asyncio
import logging
import re
import calendar

from db import DBConn
from common import site_conf

@asyncio.coroutine
def main():
    logger = logging.getLogger('')
    logger.setLevel(logging.DEBUG)
    conf = site_conf()
    _db = DBConn(conf.items('db'))
    yield from _db.connect()
    re_split = re.compile(r"\t+")
    re_split_date = re.compile(r"\D+")
    re_date = [re.compile(x) for x in [r'(\d\d\d\d)$', r'(\d?\d)\W(\d?\d?\d\d)$',\
            r'(\d?\d)\D(\d?\d)\D(\d?\d?\d\d)$']]
    re_date_l = re.compile(r'(\d?\d)\D(\d?\d)\D(\d?\d?\d\d)')
    re_date_bw = re.compile(r'(\d\d\d\d)\D(\d?\d)\D(\d?\d)')

    def parse_date(str_val, strict=True):
        str_val = str_val.strip()
        parsed = []
        if strict:
            for re_x in re_date:
                m_date = re_x.match(str_val)
                if m_date:
                    grp = 1
                    while grp <= re_x.groups:
                        parsed.append(m_date.group(grp))
                        grp += 1
        else:
            m_date = re_date_l.search(str_val)
            if m_date:
                grp = 1
                while grp < 4:
                    parsed.append(m_date.group(grp))
                    grp += 1
            else:
                m_date = re_date_bw.search(str_val)
                if m_date:
                    parsed = [m_date.group(3), m_date.group(2), m_date.group(1)]
        if parsed:
            if len(parsed[-1]) < 4:
                if len(parsed[-1]) == 3:
                    parsed = None
                else:
                    if int(parsed[-1]) < 30:
                        parsed[-1] = '20' + parsed[-1]
                    else:
                        parsed[-1] = '19' + parsed[-1]
        return parsed if parsed else None

    def compose_date(parsed_dt, end=False):
        pdt = []
        for xdt in parsed_dt:
            pdt.append(xdt)
        if len(pdt) < 2:
            pdt.insert(0, '12' if end else '01')
        if len(pdt) < 3:
            pdt.insert(0,\
                str(calendar.monthrange(int(pdt[1]), int(pdt[0]))[1]) if end\
                    else '01')
        return pdt[1] + '-' + pdt[0] + '-' + pdt[2]

    with open('/var/www/cfmrda-dev/DL6KVA.txt', 'r', encoding='cp437') as f_data:
        params = []
        for line in f_data.readlines():
            fields = [x.strip() for x in line.split('\t')]
            if fields[3] == 'DELETED':
                del fields[2]
            parsed_dt_start, parsed_dt_stop = None, None
            date = parse_date(fields[2])
            if date:
                parsed_dt_start = date
                parsed_dt_stop = date
            else:
                if '-' in fields[2]:
                    str_dates = fields[2].split('-')
                    parsed_dt_stop = parse_date(str_dates[1])
                    if parsed_dt_stop:
                        parsed_dt_start = re_split_date.split(str_dates[0])
                        if not parsed_dt_start[-1]:
                            del parsed_dt_start[-1]
                        while len(parsed_dt_start) < len(parsed_dt_stop):
                            parsed_dt_start.append(parsed_dt_stop[len(parsed_dt_start)])
                elif 'from' in fields[2] or 'SINCE' in fields[2] or 'FROM' in fields[2]:
                    str_dt_start = fields[2].replace('from ', '').replace('SINCE ',\
                        '').replace('FROM ', '')
                    parsed_dt_start = parse_date(str_dt_start)
                elif 'till' in fields[2]:
                    str_dt_stop = fields[2].replace('till ', '')
                    parsed_dt_stop = parse_date(str_dt_stop)
                if not (parsed_dt_start or parsed_dt_stop):
                    date = parse_date(fields[2], False)
                    if date:
                        parsed_dt_start = date
                        parsed_dt_stop = date
            try:
                dt_start = compose_date(parsed_dt_start) if parsed_dt_start else None
                dt_stop = compose_date(parsed_dt_stop, True) if parsed_dt_stop else None
            except Exception:
                logging.exception(fields[2])

            if len(fields[1]) != 5:
                print(fields[1])
                continue

            params.append({'callsign': fields[0], 'rda': fields[1], 'dt_start': dt_start,\
                    'dt_stop': dt_stop,\
                    'source': fields[4] if fields[4] else 'RDAWARD.org',\
                    'ts': fields[5] if fields[5] else '2019-06-17'})

        yield from _db.execute("""insert into callsigns_rda
            (callsign, rda, dt_start, dt_stop, source, ts)
            values
            (%(callsign)s, %(rda)s, %(dt_start)s, %(dt_stop)s, %(source)s, %(ts)s)""",\
            params, progress=True)

asyncio.get_event_loop().run_until_complete(main())

