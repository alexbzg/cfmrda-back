#!/usr/bin/python3
#coding=utf-8
"""script for sending cfm requests to activators"""
import asyncio
import logging

from common import site_conf, start_logging
from db import DBConn
from secret import get_secret, create_token
from send_email import send_email

def format_qsos(qsos):
    """format qso data fro email"""
    qso_tmplt = "{callsign}\t{stationCallsign}\t{tstamp}z\t{band}MHz\t{mode}\t{rcvRST}/{sntRST}\n"
    qso_txt = ""
    for qso in qsos:
        qso_txt += qso_tmplt.format_map(qso)
    return qso_txt

@asyncio.coroutine
def main():
    """sends cfm requests"""
    start_logging('send_cfm_requests')
    logging.debug('start send cfm requests')
    conf = site_conf()
    secret = get_secret(conf.get('files', 'secret'))

    _db = DBConn(conf.items('db'))
    yield from _db.connect()
    data = yield from _db.execute("""
        select correspondent, correspondent_email,
            json_agg(json_build_object('callsign', callsign, 
            'stationCallsign', station_callsign, 'rda', rda, 'band', band, 
            'mode', mode, 'tstamp', to_char(tstamp, 'DD mon YYYY HH24:MI'), 
            'rcvRST', rec_rst, 'sntRST', sent_rst)) as qso
        from
            (select * 
            from cfm_request_qso 
            where not sent) as data
        group by correspondent, correspondent_email""", None, True)
    if not data:
        return
    for row in data:
        token = create_token(secret, {'callsign': row['correspondent']})
        link_cfm = conf.get('web', 'address') + '/#/cfm_qso/?token=' + token
        link_blacklist = conf.get('web', 'address') +\
            '/#/cfm_blacklist/?token=' + token
        qso_txt = format_qsos(row['qso'])
        text = ("""
Здравствуйте, {correspondent}.

Ваши корреспонденты просят вас подтвердить проведённые с ними QSO по программе диплома RDA:
""" + qso_txt + """
Для потверждения QSO зайдите на эту страницу - {link_cfm}
Если указанные данные верны, поставьте отметки "Подтвердить" в каждом QSO и нажмите кнопку "OK"

Было бы удобнее, если бы вы зарегистрировались на CFMRDA.ru и загрузили бы свои логи в базу данных сайта.

Спасибо. 73!
Команда CFMRDA.ru


Если вы не хотите в дальнейшем получать подобные запросы на подтверждение QSO, пройдите по этой ссылке - {link_blacklist}  
И нажмите кнопку "Не присылать мне больше запросов от CFMRDA.ru"
        """).format_map({'correspondent': row['correspondent'],\
            'link_cfm': link_cfm, 'link_blacklist': link_blacklist})
        send_email(text=text,\
            fr=conf.get('email', 'address'),\
            to=row['correspondent_email'],\
            subject="Запрос на подтверждение QSO от CFMRDA.ru")
    yield from _db.execute("""
        update cfm_request_qso 
        set sent = true
        where correspondent = %(correspondent)s""",\
        data)
    yield from _db.execute("""
        update cfm_requests 
        set tstamp = now()
        where callsign = %(correspondent)s;
        insert into cfm_requests
        select %(correspondent)s, now()
        where not exists
            (select 1 
            from cfm_requests 
            where callsign = %(correspondent)s)
        """, data)

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())

