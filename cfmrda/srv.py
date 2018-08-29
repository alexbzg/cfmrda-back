#!/usr/bin/python3
#coding=utf-8

import asyncio
import logging
import time
import base64

from aiohttp import web
import jwt

from common import site_conf, start_logging
from db import DBConn
import send_email
from secret import secret
import recaptcha
from json_utils import load_json, JSONvalidator
from qrz import QRZComLink

start_logging('srv')
logging.debug("restart")

class CfmRdaServer():
    DEF_ERROR_MSG = 'Ошибка сайта. Пожалуйста, попробуйте позднее.'

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
    def adif_hndlr(self, request):
        error = None
        data = yield from request.json()
        if self._json_validator.validate('adif', data):
            callsign = self.decode_token(data)
            if isinstance(callsign, str):
                user_data = yield from self.get_user_data(callsign)
                if user_data['email_confirmed']:
                    file = base64.b64decode(data['file'].split(',')[1])
                    file_rec = yield from self._db.execute(\
                        "insert into uploads (user, rda, station_callsign) " + \
                        "values (%(callsign)s, %(rda)s, %(station_callsign)s)" + \
                        "returning id",\
                        {'callsign': callsign,\
                        'rda': data['rda'],\
                        'station_callsign': data['stationCallsign']})
                    logging.debug(file_rec)
                    for line in file:
                        logging.debug(line)
                else:
                    error = 'Ваш адрес электронной почты не подтвержден.'
            else:
                return callsign
        else:
            error = CfmRdaServer.DEF_ERROR_MSG
        if error:
            return web.HTTPBadRequest(text=error)
        else:
            return web.Response(text='OK')

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
            + '/aiohttp/confirm_emai?token=' + token + """

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
                error = 'Проверка на робота не пройдена или данные устарели. Попробуйте еще раз.'
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
            return web.Response(text='Ваш адрес электронной почты был подвержден.')
        else:
            return callsign

    def decode_token(self, data, check_time=False):
        callsign = None
        if 'token' in data:
            try:
                payload = jwt.decode(data['token'], self._secret, algorithms=['HS256'])
            except jwt.exceptions.DecodeError:
                return web.HTTPBadRequest(text='Токен просрочен. Пожалуйста, повторите операцию.')
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
    APP = web.Application(client_max_size=10 * 1024 ** 2)
    SRV = CfmRdaServer(APP.loop)
    APP.router.add_get('/aiohttp/test', test_hndlr)
    APP.router.add_post('/aiohttp/test', test_hndlr)
    APP.router.add_post('/aiohttp/login', SRV.login_hndlr)
    APP.router.add_post('/aiohttp/contact_support', SRV.contact_support_hndlr)
    APP.router.add_get('/aiohttp/confirm_emai', SRV.cfm_email_hndlr)
    web.run_app(APP, path=SRV.conf.get('files', 'server_socket'))
