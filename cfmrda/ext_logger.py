#!/usr/bin/python3
#coding=utf-8
"""class for working with web-loggers. Currenly supported: LOTW"""

import requests

class ExtLogger():

    def __init__(self, logger_type):
        self.type = logger_type

    def login(self, login_data):
        ssn = requests.Session()
        rsp = None
        if self.type == 'LOTW':
            ssn.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.131 Safari/537.36'})
            data = {\
                'acct_sel': '',\
                'thisForm': 'login'\
            }
            data.update(login_data)

            rsp = ssn.post('https://lotw.arrl.org/lotwuser/login', data=data)
        rsp.raise_for_status()

        return ssn

    def download(self, login_data, **kwparams):
        ssn = self.login(login_data)

        rsp = ssn.get('https://lotw.arrl.org/lotwuser/lotwreport.adi?qso_query=1&qso_withown=yes&qso_qslsince=' +\
                kwparams['date_from'] +'&qso_owncall=')
        rsp.raise_for_status()

        return rsp.text

