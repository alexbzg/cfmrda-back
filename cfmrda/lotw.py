#!/usr/bin/python3
#coding=utf-8

import requests

ssn = requests.Session()
ssn.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.131 Safari/537.36'})

ssn.post('https://lotw.arrl.org/lotwuser/login',\
        data={\
            'login': '',\
            'password': '',\
            'acct_sel': '',\
            'thisForm': 'login'\
            }\
            )

rsp = ssn.get('https://lotw.arrl.org/lotwuser/lotwreport.adi?qso_query=1&qso_withown=yes&qso_qslsince=2019-04-01&qso_owncall=')

with open('/usr/local/cfmrda-dev/_lotw.adi', 'w') as f:
    f.write(rsp.text)
