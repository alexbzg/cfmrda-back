#!/usr/bin/python3
#coding=utf-8

import asyncio
import logging
import time

from aiohttp import web
import jwt
import jsonschema

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
        if 'register' in data:
            return (yield from self.register_user(data))
        else:
            return (yield from self.login((data)))

    @asyncio.coroutine
    def register_user(self, data):
        error = None
        try:
            self._json_validator.validate('register', data)
            rc_test = yield from recaptcha.check_recaptcha(data['recaptcha'])
            if rc_test:
                test_callsign = yield from self.get_user_data(data['callsign'])
                if test_callsign:
                    error = 'Этот позывной уже зарегистрирован.'
                else:
                    qrz_data = self._qrzcom.get_data(data['callsign'])
                    if qrz_data and qrz_data['email'] == data['email']:
                        yield from self._db.get_object('users',\
                            {'callsign': data['callsign'],\
                            'password': data['password'],\
                            'email': data['email'],\
                            'email_confirmed': False},\
                            True)
                        token = self.create_token(\
                            {'callsign': data['callsign'], 'time': time.time()})
                        text = """
Пройдите по ссылкe, чтобы подтвердить свою электроную почту на CFMRDA.ru:

""" \
                            + self.conf.get('web', 'address')\
                            + '/aiohttp/confirmEmail?token=' + token + """

Если вы не регистрировали учетную запись на CFMRDA.ru, просто игнорируйте это письмо.
Ссылка будет действительна в течение 1 часа.

Служба поддержки CFMRDA.ru"""
                        send_email.send_email(text=text,\
                            fr=self.conf.get('email', 'address'),\
                            to=data['email'],\
                            subject="CFMRDA.ru - подтверждение электронной почты")
                    else:
                        error =\
                            'Позывной или адрес электронной почты не зарегистрирован на QRZ.com'
            else:
                error = 'Проверка на робота не пройдена или данные устарели. Попробуйте еще раз.'
        except jsonschema.exceptions.ValidationError:
            error = 'Ошибка сайта. Пожалуйста, попробуйте позднее.'
        if error:
            return web.HTTPBadRequest(text=error)
        else:
            return (yield from self.send_user_data(data['callsign']))

    @asyncio.coroutine
    def login(self, data):
        error = None
        try:
            self._json_validator.validate('login', data)
            user_data = yield from self.get_user_data(data['callsign'])
            if user_data and user_data['password'] == data['password']:
                return (yield from self.send_user_data(data['callsign']))
            else:
                error = 'Неверный позывной или пароль'
        except jsonschema.exceptions.ValidationError:
            error = 'Ошибка сайта. Пожалуйста, попробуйте позднее.'
        if error:
            return web.HTTPBadRequest(text=error)

    @asyncio.coroutine
    def send_user_data(self, callsign):
        user_data = yield from self.get_user_data(callsign)
        user_data['token'] = self.create_token({'callsign': callsign})
        del user_data['password']
        return web.json_response(user_data)

    @asyncio.coroutine
    def pwd_recovery_req_hndlr(self, request):
        error = None
        data = yield from request.json()
        user_data = False
        if 'login' not in data or len(data['login']) < 2:
            error = 'Minimal login length is 2 symbols'
        if not error:
            data['login'] = data['login'].lower()
            rc_test = yield from recaptcha.check_recaptcha(data['recaptcha'])
            user_data = yield from self.get_user_data(data['login'])
            if not rc_test:
                error = 'Recaptcha test failed. Please try again'
            else:
                if not user_data:
                    error = 'This callsign is not registered.'
                else:
                    if not user_data['email']:
                        error = 'This account has no email address.'
                    else:
                        token = self.create_token({'callsign': data['login'], 'time': time.time()})
                        text = 'Пройдите по ссылке, чтобы восстановить свой пароль ' + \
                                'на CFMRDA.ru:' + self.conf.get('web', 'address') + \
                                '/aiohttp/changePassword?token=' + token + """
    Если вы не запрашивали восстановление пароля, просто игнорируйте это письмо.
    Ссылка будет действительна в течение 1 часа.

    Служба поддержки CFMRDA.ru"""
                        send_email.send_email(text=text, fr=self.conf.get('email', 'address'), \
                            to=user_data['email'], \
                            subject="tnxqso.com password recovery")
                        return web.Response(text='OK')
        return web.HTTPBadRequest(text=error)

    @asyncio.coroutine
    def cfm_email_hndlr(self, request):
        data = request.query
        callsign = self.decode_token(data, check_time=True)
        if isinstance(callsign, str):
            yield from self._db.param_update('users', {'callsign': callsign},\
                {'email_confirmed': True})
            return web.HTTPFound(self.conf.get('web', 'address'))
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
    APP.router.add_get('/aiohttp/confirm_email', SRV.cfm_email_hndlr)
    web.run_app(APP, path=SRV.conf.get('files', 'server_socket'))
