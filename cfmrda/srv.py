#!/usr/bin/python3
#coding=utf-8

import asyncio
import logging
import time

from aiohttp import web
import jwt

from common import siteConf, startLogging
from db import DBConn
from sendEmail import sendEmail
from secret import secret
from recaptcha import checkRecaptcha

startLogging('srv')
logging.debug("restart")

class CfmRdaServer():

    def __init__(self, app):
        self._app = app
        self.conf = siteConf()
        self._db = DBConn(self.conf.items('db'))
        asyncio.async(self._db.connect())
        self.secret = secret(self.conf.get('files', 'secret'))

    @asyncio.coroutine
    def get_user_data(self, callsign):
        return (yield from self._db.getObject('users', \
                {'callsign': callsign}, False, True))
        
    @asyncio.coroutine
    def pwd_recovery_req_hndlr(self, request):
        error = None
        data = yield from request.json()
        user_data = False
        if 'login' not in data or len(data['login']) < 2:
            error = 'Minimal login length is 2 symbols'
        if not error:
            data['login'] = data['login'].lower()
            rc_test = yield from checkRecaptcha(data['recaptcha'])
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
                        token = jwt.encode({'callsign': data['login'], 'time': time.time()}, \
                            secret, algorithm='HS256').decode('utf-8')
                        text = 'Click on this link to recover your tnxqso.com ' + \
                                'password:' + self.conf.get('web', 'address') + \
                                '/#/changePassword?token=' + token + """
    If you did not request password recovery just ignore this message. 
    The link above will be valid for 1 hour.

    tnxqso.com support"""
                        sendEmail(text=text, fr=self.conf.get('email', 'address'), \
                            to=user_data['email'], \
                            subject="tnxqso.com password recovery")
                        return web.Response(text='OK')
        return web.HTTPBadRequest(text=error)

@asyncio.coroutine
def test_get_handler(request):
    return web.Response(text='OK')


def decode_token(data):
    callsign = None
    if 'token' in data:
        try:
            payload = jwt.decode(data['token'], secret, algorithms=['HS256'])
        except jwt.exceptions.DecodeError:
            return web.HTTPBadRequest(text='Login expired')
        if 'callsign' in payload:
            callsign = payload['callsign'].lower()
        if 'time' in payload and time.time() - payload['time'] > 60 * 60:
            return web.HTTPBadRequest(text='Password change link is expired')
    return callsign if callsign else web.HTTPBadRequest(text='Not logged in')

if __name__ == '__main__':
    APP = web.Application(client_max_size=10 * 1024 ** 2)
    SRV = CfmRdaServer(APP)
    APP.router.add_get('/aiohttp/test', test_get_handler)
    web.run_app(APP, path=SRV.conf.get('files', 'server_socket'))
