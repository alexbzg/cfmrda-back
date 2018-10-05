#!/usr/bin/python3
#coding=utf-8

import asyncio
import logging
import time
import base64
import re
import hashlib

from aiohttp import web
import jwt
import chardet

from common import site_conf, start_logging
from db import DBConn
import send_email
from secret import secret
import recaptcha
from json_utils import load_json, JSONvalidator
from qrz import QRZComLink
from ham_radio import load_adif, ADIFParseException, strip_callsign
from export import export_rankings, export_recent_uploads, export_msc

start_logging('srv')
logging.debug("restart")

class CfmRdaServer():
    DEF_ERROR_MSG = 'Ошибка сайта. Пожалуйста, попробуйте позднее.'
    RECAPTCHA_ERROR_MSG = 'Проверка на робота не пройдена или данные устарели. Попробуйте еще раз.'

    def __init__(self, loop):
        self._loop = loop
        self.conf = site_conf()
        self._db = DBConn(self.conf.items('db'))
        self._qrzcom = QRZComLink(loop)
        asyncio.async(self._db.connect())
        self._secret = secret(self.conf.get('files', 'secret'))
        self._json_validator = JSONvalidator(\
            load_json(self.conf.get('web', 'root') + '/json/schemas.json'))

    def create_token(self, data):
        return jwt.encode(data, self._secret, algorithm='HS256').decode('utf-8')

    @asyncio.coroutine
    def get_user_data(self, callsign):
        return (yield from self._db.get_object('users', \
                {'callsign': callsign}, False, True))

    @asyncio.coroutine
    def login_hndlr(self, request):
        data = yield from request.json()
        if 'mode' in data:
            if data['mode'] == 'register':
                return (yield from self.register_user(data))
            elif data['mode'] == 'login':
                return (yield from self.login(data))
            elif data['mode'] == 'passwordRequest':
                return (yield from self.password_request(data))
            elif data['mode'] == 'passwordChange':
                return (yield from self.password_change(data))
            elif data['mode'] == 'emailRequest':
                return (yield from self.email_request(data))
        logging.debug(data)
        return web.HTTPBadRequest(text=CfmRdaServer.DEF_ERROR_MSG)

    @asyncio.coroutine
    def contact_support_hndlr(self, request):
        data = yield from request.json()
        if self._json_validator.validate('contactSupport', data):
            email = None
            callsign = None
            if 'token' in data:
                callsign = self.decode_token(data)
                if isinstance(callsign, str):
                    user_data = yield from self.get_user_data(callsign)
                    email = user_data['email']
                else:
                    return callsign
            else:
                rc_test = yield from recaptcha.check_recaptcha(data['recaptcha'])
                if not rc_test:
                    return web.HTTPBadRequest(text=CfmRdaServer.RECAPTCHA_ERROR_MSG)
                email = data['email']
            send_email.send_email(text=data['text'],\
                to=self.conf.get('email', 'address'),\
                fr=email,\
                subject="CFMRDA.ru support" + \
                    (' (' + callsign + ')' if callsign else ''))
            return web.Response(text='OK')

        return web.HTTPBadRequest(text=CfmRdaServer.DEF_ERROR_MSG)

    @asyncio.coroutine
    def email_request(self, data):
        callsign = self.decode_token(data)
        if isinstance(callsign, str):
            yield from self._db.param_update('users', {'callsign': callsign},\
                {'email_confirmed': True})
            return web.HTTPFound(self.conf.get('web', 'address'))
        else:
            return callsign

    @asyncio.coroutine
    def load_adif_file(self, file, callsign, activators=None,\
            station_callsign=None, station_callsign_field=None):
        error = {'filename': file['name'],\
                'rda': file['rda'],\
                'message': 'Ошибка загрузки'}
        try:
            adif_bytes = \
                base64.b64decode(file['file'].split(',')[1])
            adif_hash = hashlib.md5(adif_bytes).hexdigest()
            hash_check = yield from self._db.execute("""
                select id from uploads where hash = %(hash)s
            """, {'hash': adif_hash})
            if hash_check:
                error['message'] = "Файл уже загружен"
                return error
            adif_enc = chardet.detect(adif_bytes)
            adif = adif_bytes.decode(adif_enc['encoding'])
            adif_data = load_adif(adif, \
                station_callsign_field=station_callsign_field)
            logging.debug(adif_data)

            file_rec = yield from self._db.execute("""
                insert into uploads
                    (user_cs, rda, date_start, date_end, hash)
                values (%(callsign)s, %(rda)s,
                    %(date_start)s, %(date_end)s, %(hash)s)
                returning id""",\
                {'callsign': callsign,\
                'rda': file['rda'],\
                'date_start': adif_data['date_start'],\
                'date_end': adif_data['date_end'],\
                'hash': adif_hash})
            if not file_rec:
                raise Exception()
            logging.debug('Upload id: ' + str(file_rec['id']))

            act_sql = """insert into activators
                values (%(upload_id)s, %(activator)s)"""
            act_params = [{'upload_id': file_rec['id'],\
                'activator': act} for act in activators]
            if adif_data['activator']:
                act_params.append({'upload_id': file_rec['id'],\
                    'activator': adif_data['activator']})
            res = yield from self._db.execute(act_sql, act_params)
            if not res:
                raise Exception()

            qso_sql = """insert into qso
                (upload_id, callsign, station_callsign, rda,
                    band, mode, tstamp)
                values (%(upload_id)s, %(callsign)s,
                    %(station_callsign)s, %(rda)s, %(band)s,
                    %(mode)s, %(tstamp)s)"""
            qso_params = []
            for qso in adif_data['qso']:
                qso_params.append({'upload_id': file_rec['id'],\
                    'callsign': qso['callsign'],\
                    'station_callsign': station_callsign or \
                        qso['station_callsign'],\
                    'rda': file['rda'],\
                    'band': qso['band'],\
                    'mode': qso['mode'],\
                    'tstamp': qso['tstamp']})
            res = yield from self._db.execute(qso_sql, qso_params)
            if res:
                return None
            else:
                raise Exception()
        except Exception as exc:
            if isinstance(exc, ADIFParseException):
                error['message'] = str(exc)
            logging.exception('ADIF load error')
            return error


    @asyncio.coroutine
    def adif_hndlr(self, request):
        data = yield from request.json()
        if self._json_validator.validate('adif', data):
            callsign = self.decode_token(data)
            if isinstance(callsign, str):
                user_data = yield from self.get_user_data(callsign)
                if user_data['email_confirmed']:
                    station_callsign_field = None
                    station_callsign = None
                    activators = set([])
                    response = {'filesLoaded': 0, 'errors': []}
                    if data['stationCallsignFieldEnable']:
                        station_callsign_field = data['stationCallsignField']
                    else:
                        station_callsign = data['stationCallsign']
                        activators.add(station_callsign)
                    if 'additionalActivators' in data and\
                        data['additionalActivators']:
                        for act_cs in re.split(r"(?:\s|,|;)",\
                            data["additionalActivators"]):
                            activator = strip_callsign(act_cs)
                            if activator:
                                activators.add(activator)
                    for file in data['files']:
                        error = yield from self.load_adif_file(file, callsign,\
                                activators=activators,\
                                station_callsign=station_callsign,\
                                station_callsign_field=station_callsign_field)
                        if error:
                            response['errors'].append(error)
                        else:
                            response['filesLoaded'] += 1
                    if response['filesLoaded'] and 'skipRankings' not in data:
                        logging.debug('running export_rankings')
                        yield from export_rankings(self.conf)
                        yield from export_recent_uploads(self.conf)
                        yield from export_msc(self.conf)
                    logging.debug(response)
                    return web.json_response(response)
                else:
                    return web.HTTPBadRequest(text='Ваш адрес электронной почты не подтвержден.')
            else:
                return callsign
        else:
            return web.HTTPBadRequest(text=CfmRdaServer.DEF_ERROR_MSG)

    @asyncio.coroutine
    def password_request(self, data):
        error = None
        if self._json_validator.validate('passwordRequest', data):
            rc_test = yield from recaptcha.check_recaptcha(data['recaptcha'])
            if rc_test:
                user_data = yield from self.get_user_data(data['callsign'])
                if user_data:
                    token = self.create_token(\
                        {'callsign': data['callsign'], 'time': time.time()})
                    text = """Пройдите по ссылкe, чтобы сменить пароль на CFMRDA.ru:

""" \
                        + self.conf.get('web', 'address')\
                        + '/#/login?token=' + token + """

Если вы не запрашивали смену пароля на CFMRDA.ru, просто игнорируйте это письмо.
Ссылка будет действительна в течение 1 часа.

Служба поддержки CFMRDA.ru"""
                    send_email.send_email(text=text,\
                        fr=self.conf.get('email', 'address'),\
                        to=user_data['email'],\
                        subject="CFMRDA.ru - смена пароля")
                else:
                    error =\
                        'Позывной не зарегистрирован на CFMRDA.ru'
            else:
                error = 'Проверка на робота не пройдена или данные устарели. Попробуйте еще раз.'
        else:
            error = CfmRdaServer.DEF_ERROR_MSG
        if error:
            return web.HTTPBadRequest(text=error)
        else:
            return web.Response(text='OK')

    @asyncio.coroutine
    def password_change(self, data):
        if self._json_validator.validate('passwordChange', data):
            callsign = self.decode_token(data, check_time=True)
            if isinstance(callsign, str):
                yield from self._db.param_update('users', {'callsign': callsign},\
                    {'email_confirmed': True, 'password': data['password']})
                return web.Response(text='OK')
            else:
                return callsign
        else:
            return web.HTTPBadRequest(text=CfmRdaServer.DEF_ERROR_MSG)

    def send_email_cfm(self, callsign, email):
        token = self.create_token(\
            {'callsign': callsign, 'time': time.time()})
        text = """Пройдите по ссылкe, чтобы подтвердить свою электроную почту на CFMRDA.ru:

""" \
            + self.conf.get('web', 'address')\
            + '/aiohttp/confirm_email?token=' + token + """

Если вы не регистрировали учетную запись на CFMRDA.ru, просто игнорируйте это письмо.
Ссылка будет действительна в течение 1 часа.

Служба поддержки CFMRDA.ru"""
        send_email.send_email(text=text,\
            fr=self.conf.get('email', 'address'),\
            to=email,\
            subject="CFMRDA.ru - подтверждение электронной почты")

    @asyncio.coroutine
    def register_user(self, data):
        error = None
        if self._json_validator.validate('register', data):
            rc_test = yield from recaptcha.check_recaptcha(data['recaptcha'])
            if rc_test:
                test_callsign = yield from self.get_user_data(data['callsign'])
                if test_callsign:
                    error = 'Этот позывной уже зарегистрирован.'
                else:
                    qrz_data = self._qrzcom.get_data(data['callsign'])
                    if qrz_data and 'email' in qrz_data and \
                        qrz_data['email'] == data['email']:
                        yield from self._db.get_object('users',\
                            {'callsign': data['callsign'],\
                            'password': data['password'],\
                            'email': data['email'],\
                            'email_confirmed': False},\
                            True)
                        self.send_email_cfm(data['callsign'], data['email'])
                    else:
                        error =\
                            'Позывной или адрес электронной почты не зарегистрирован на QRZ.com'
            else:
                error = CfmRdaServer.RECAPTCHA_ERROR_MSG
        else:
            error = CfmRdaServer.DEF_ERROR_MSG
        if error:
            return web.HTTPBadRequest(text=error)
        else:
            return web.Response(text='OK')

    @asyncio.coroutine
    def login(self, data):
        error = None
        if self._json_validator.validate('login', data):
            user_data = yield from self.get_user_data(data['callsign'])
            if user_data and user_data['password'] == data['password']:
                if user_data['email_confirmed']:
                    return (yield from self.send_user_data(data['callsign']))
                else:
                    error = 'Необходимо подтвердить адрес электронной почты. ' +\
                            'Вам отправлено повторное письмо с инструкциями.'
                    self.send_email_cfm(data['callsign'], user_data['email'])
            else:
                error = 'Неверный позывной или пароль.'
        else:
            error = CfmRdaServer.DEF_ERROR_MSG
        if error:
            return web.HTTPBadRequest(text=error)

    @asyncio.coroutine
    def send_user_data(self, callsign):
        user_data = yield from self.get_user_data(callsign)
        user_data['token'] = self.create_token({'callsign': callsign})
        del user_data['password']
        return web.json_response(user_data)

    @asyncio.coroutine
    def cfm_email_hndlr(self, request):
        data = request.query
        callsign = self.decode_token(data, check_time=True)
        if isinstance(callsign, str):
            yield from self._db.param_update('users', {'callsign': callsign},\
                {'email_confirmed': True})
            return web.Response(text='Ваш адрес электронной почты был подтвержден.')
        else:
            return callsign

    @asyncio.coroutine
    def hunter_hndlr(self, request):
        callsign = request.match_info.get('callsign', None)
        if callsign:
            qso = yield from self._db.execute("""
                select json_object_agg(rda, data) as data
                from
                    (select rda, json_object_agg(type, data) as data
                    from
                        (select qso.rda, 'hunter' as type,
                            json_agg(json_build_object('band', band,
                                'mode', mode,
                                'date', to_char(qso.tstamp, 'DD Month YYYY'),
                                'time', to_char(qso.tstamp, 'HH24:MI'),
                                'stationCallsign', station_callsign,
                                'uploadId', uploads.id,
                                'uploader', uploads.user_cs)) as data
                        from qso, uploads
                        where callsign = %(callsign)s and enabled 
                            and qso.upload_id = uploads.id
                        group by qso.rda
                        union all
                        select rda, 'activator' as type,
                            json_agg(json_build_object('mode', mode,
                                'band', band,
                                'date', to_char(dt, 'DD Month YYYY'),
                                'uploadId', upload_id,
                                'uploader', uploader, 'count', count)) as data
                        from
                            (select mode, band, qso.rda, dt, count(distinct callsign), 
                                qso.upload_id,
                                (select user_cs 
                                from uploads 
                                where id = qso.upload_id) as uploader
                            from qso, uploads, activators
                            where uploads.id = qso.upload_id and enabled
                                and activators.upload_id = qso.upload_id 
                                and activator = %(callsign)s
                            group by qso.upload_id, mode, band, qso.rda, dt) as l_0
                        group by rda) as l_1
                    group by rda) as l_2
            """, {'callsign': callsign}, False)
            if qso:
                rank = yield from self._db.execute("""
                select rankings_json('callsign = '%(callsign)s'') as data
                """, {'callsign': callsign}, False)
                return web.json_response({'qso': qso['data'], 'rank': rank['data']})
            else:
                return web.json_response(False)
        else:
            return web.HTTPBadRequest(text='Необходимо ввести позывной')

    @asyncio.coroutine
    def view_upload_hndlr(self, request):
        upload_id = request.match_info.get('id', None)
        if upload_id:
            qso = (yield from self._db.execute("""
                select json_agg(json_build_object('callsign', callsign, 
                    'stationCallsign', station_callsign, 'rda', rda, 
                    'band', band, 'mode', mode, 
                    'date', to_char(tstamp, 'DD Month YYYY'),
                    'time', to_char(tstamp, 'HH24:MI')))
                    as data
                from 
                    (select callsign, station_callsign, rda, 
                        band, mode, tstamp
                    from qso 
                    where upload_id = %(upload_id)s
                    order by tstamp) as l_0
            """, {'upload_id': upload_id}, False))['data']
            if qso:
                return web.json_response(qso)
            else:
                return web.json_response(False)
        else:
            return web.HTTPBadRequest(text='Необходимо ввести id файла')

    def decode_token(self, data, check_time=False):
        callsign = None
        if 'token' in data:
            try:
                payload = jwt.decode(data['token'], self._secret,\
                    algorithms=['HS256'])
            except jwt.exceptions.DecodeError:
                return web.HTTPBadRequest(\
                    text='Токен просрочен. Пожалуйста, повторите операцию.')
            if 'callsign' in payload:
                callsign = payload['callsign'].upper()
            if check_time:
                if 'time' not in payload or time.time() - payload['time'] > 60 * 60:
                    return web.HTTPBadRequest(\
                        text='Токен просрочен. Пожалуйста, повторите операцию.')
        return callsign if callsign\
            else web.HTTPBadRequest(text='Необходимо войти в учетную запись.')


@asyncio.coroutine
def test_hndlr(request):
    if request.method == 'POST':
        data = yield from request.json()
        return web.json_response(data)
    return web.Response(text='OK')

if __name__ == '__main__':
    APP = web.Application(client_max_size=100 * 1024 ** 2)
    SRV = CfmRdaServer(APP.loop)
    APP.router.add_get('/aiohttp/test', test_hndlr)
    APP.router.add_post('/aiohttp/test', test_hndlr)
    APP.router.add_post('/aiohttp/login', SRV.login_hndlr)
    APP.router.add_post('/aiohttp/contact_support', SRV.contact_support_hndlr)
    APP.router.add_post('/aiohttp/adif', SRV.adif_hndlr)
    APP.router.add_get('/aiohttp/confirm_email', SRV.cfm_email_hndlr)
    APP.router.add_get('/aiohttp/hunter/{callsign}', SRV.hunter_hndlr)
    APP.router.add_get('/aiohttp/upload/{id}', SRV.view_upload_hndlr)
    web.run_app(APP, path=SRV.conf.get('files', 'server_socket'))
