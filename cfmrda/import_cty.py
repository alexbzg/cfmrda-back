#!/usr/bin/python3
#coding=utf-8
"""imports selected countries prefixes to db"""
import asyncio
import logging
import argparse
import os
import re
import sys

from common import site_conf
from db import DBConn

@asyncio.coroutine
def import_cty(conf, cty_path):
    """rebuild rankings table in db and export top100 to json file for web"""
    logging.debug('import country prefixes')

    _db = DBConn(conf.items('db'))
    yield from _db.connect()
    re_country = re.compile(r"\s\*?(\S+):$")
    re_pfx = re.compile(r"(\(.*\))?(\[.*\])?")
    countries = {}
    for country, pfxs in conf.items('countries'):
        country_id = yield from _db.execute("""
            insert into countries (name)
            values (%(country)s)
            returning id""", {'country': country})
        for pfx in pfxs.split(','):
            countries[pfx] = country_id
    with open(cty_path, 'r') as f_cty:
        cur_country_id = None
        for line in f_cty.readlines():
            line = line.rstrip('\r\n')
            m_country = re_country.search(line)
            if m_country:
                cur_pfx_main = m_country.group(1)
                cur_country_id = countries[cur_pfx_main] if cur_pfx_main in countries else None
            elif cur_country_id:
                pfxs = line.lstrip(' ').rstrip(';,').split(',')
                for pfx in pfxs:
                    pfx0 = re_pfx.sub("", pfx)
                    if not pfx0.startswith("="):
                        yield from _db.execute("""
                            insert into country_prefixes (prefix, country_id)                            
                            values (%(prefix)s, %(country_id)s)""",\
                            {'prefix': pfx0,
                             'country_id': cur_country_id})

def main():
    """when called from shell imports countries prefixes to db"""
    conf = site_conf()

    parser = argparse.ArgumentParser()
    parser.add_argument('path')
    args = parser.parse_args()

    if not args.path:
        sys.exit('Path is required.')

    if not os.path.isfile(args.path):
        sys.exit('Path does not exist')

    asyncio.get_event_loop().run_until_complete(import_cty(conf, args.path))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logging.exception('Import exception')
