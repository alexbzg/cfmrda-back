#!/usr/bin/python3
#coding=utf-8
"""class for working with web-loggers. Currenly supported: LOTW"""
import re
import datetime

import requests

from ham_radio import RDA_START_DATE

class ExtLoggerException(Exception):
    """Login failed"""
    pass

def eqsl_date_format(_dt):
    """formats date for eqsl url params: mm%2Fdd%2Fyyyy"""
    return _dt.strftime('%m%%2F%d%%2F%Y')

class ExtLogger():

    default_login_data_fields = ['login', 'password']

    types = {'LoTW': {},\
            'eQSL': {\
                 'loginDataFields': ['Callsign', 'EnteredPassword'],\
                 'schema': 'extLoggersLoginEQSL'\
                }\
            }

    states = {0: 'OK',\
            1: 'Не удалось войти на сайт. Login attempt failed'}

    def __init__(self, logger_type):
        self.type = logger_type

    def login(self, login_data):
        ssn = requests.Session()
        rsp = None
        ssn.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.131 Safari/537.36'})
        data = {}
        data.update(login_data)
        if self.type == 'LoTW':
            data.update({\
                'acct_sel': '',\
                'thisForm': 'login'\
            })

            rsp = ssn.post('https://lotw.arrl.org/lotwuser/login', data=data)
            rsp.raise_for_status()
            if 'Username/password incorrect' in rsp.text:
                raise ExtLoggerException("Login failed.")

        elif self.type == 'HAMLOG':
            rsp = ssn.post('https://hamlog.ru/lk/login.php', data=data)
            rsp.raise_for_status()
            if 'Ошибка! Неверный адрес и/или пароль' in rsp.text:
                raise ExtLoggerException("Login failed.")

        elif self.type == 'eQSL':
            data.update({\
                'Login': 'Go'\
            })
            rsp = ssn.post('https://www.eqsl.cc/QSLCard/LoginFinish.cfm', data=data)
            rsp.raise_for_status()
            if 'Callsign or Password Error!' in rsp.text:
                raise ExtLoggerException("Login failed.")

        return ssn

    def load(self, login_data, **kwparams):
        ssn = self.login(login_data)
        adifs = []

        if self.type == 'LoTW':
            rsp = ssn.get('https://lotw.arrl.org/lotwuser/lotwreport.adi?qso_query=1&qso_withown=yes' +\
                ('&qso_qslsince=' + kwparams['date_from']\
                    if 'date_from' in kwparams and kwparams['date_from']\
                    else '') + '&qso_owncall=')
            rsp.raise_for_status()

            adifs.append(rsp.text)

        elif self.type == 'HAMLOG':
            rsp = ssn.get('https://hamlog.ru/lk/calls.php')
            rsp.raise_for_status()

            re_adif = re.compile(r'dl\.php\?c=(\d+)')
            data = {'dluser': 0, 'dlmode': 'ANY', 'edit': 'Скачать лог'}
            for mo_adif in re_adif.finditer(rsp.text):
                rsp_adif = ssn.post('https://hamlog.ru/lk/download.php?c=' + mo_adif.group(1),\
                        data=data)
                rsp_adif.raise_for_status()
                adifs.append(rsp_adif.text)

        elif self.type == 'eQSL':
            re_adif = re.compile(r'downloadedfiles/(.*)\.adi')

            def get_eqsl_adifs(date_from, date_till):
                rsp = ssn.get('https://www.eqsl.cc/QSLCard/DownloadInbox.cfm?LimitDateLo=' +\
                   eqsl_date_format(date_from) + '&LimitDateHi=' +\
                   eqsl_date_format(date_till))
                rsp.raise_for_status()
                if 'You can only download 50000 records at one time' in rsp.text:
                    date_mid = date_from + (date_till - date_from) / 2
                    get_eqsl_adifs(date_from, date_mid)
                    get_eqsl_adifs(date_mid, date_till)
                else:
                    mo_adif = re_adif.search(rsp.text)
                    if mo_adif:
                        rsp_adif = ssn.get('https://www.eqsl.cc/qslcard/downloadedfiles/' +\
                            mo_adif.group(1) + '.adi')
                        rsp_adif.raise_for_status()
                        adifs.append(rsp_adif.text)

            get_eqsl_adifs(RDA_START_DATE, datetime.date.today())

        return adifs
