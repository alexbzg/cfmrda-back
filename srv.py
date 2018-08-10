#!/usr/bin/python3
#coding=utf-8

import asyncio, logging, aiohttp, jwt, os, base64, json, time, smtplib, io
from datetime import datetime
from aiohttp import web
from common import siteConf, loadJSON, appRoot, startLogging
from db import DBConn, spliceParams
from sendEmail import sendEmail
from secret import secret
from recaptcha import checkRecaptcha

startLogging( 'srv' )
logging.debug( "restart" )

class CfmRdaServer():

    def __init__(self, app):
        self.app = app
        self.conf = siteConf()
        self.db = DBConn( self.conf.items( 'db' ) )
        asyncio.async( self.db.connect() )
        self.secret = secret( self.conf.get( 'files', 'secret' ) )

    @asyncio.coroutine
    def getUserData( self, callsign ):
        return ( yield from self.db.getObject( 'users', \
                { 'callsign': callsign }, False, True ) )

    @asyncio.coroutine
    def passwordRecoveryRequestHandler(self, request):
        error = None
        data = yield from request.json()
        userData = False
        if not 'login' in data or len( data['login'] ) < 2:
            error = 'Minimal login length is 2 symbols'
        if not error:
            data['login'] = data['login'].lower()
            rcTest = yield from checkRecaptcha( data['recaptcha'] )
            userData = yield from getUserData( data['login'] )
            if not rcTest:
                error = 'Recaptcha test failed. Please try again'
            else:
                if not userData:
                    error = 'This callsign is not registered.'
                else:
                    if not userData['email']:
                        error = 'This account has no email address.'
                    else:
                        token = jwt.encode( 
                            { 'callsign': data['login'], 'time': time.time() }, \
                            secret, algorithm='HS256' ).decode('utf-8')
                        text = 'Click on this link to recover your tnxqso.com ' + \
                                'password:' + webAddress + \
                                '/#/changePassword?token=' + token + """
    If you did not request password recovery just ignore this message. 
    The link above will be valid for 1 hour.

    tnxqso.com support"""
                        sendEmail( text = text, fr = conf.get( 'email', 'address' ), \
                            to = userData['email'], \
                            subject = "tnxqso.com password recovery" )
                        return web.Response( text = 'OK' )
        return web.HTTPBadRequest( text = error )

    @asyncio.coroutine
    def testGetHandler(self, request):
        return web.Response( text = 'OK' )


def decodeToken( data ):
    callsign = None
    if 'token' in data:
        try:
            pl = jwt.decode( data['token'], secret, algorithms=['HS256'] )
        except jwt.exceptions.DecodeError as e:
            return web.HTTPBadRequest( text = 'Login expired' )
        if 'callsign' in pl:
            callsign = pl['callsign'].lower()
        if 'time' in pl and time.time() - pl['time'] > 60 * 60:
            return web.HTTPBadRequest( text = 'Password change link is expired' )
    return callsign if callsign else web.HTTPBadRequest( text = 'Not logged in' )

if __name__ == '__main__':
    app = web.Application( client_max_size = 10 * 1024 ** 2 )
    srv = CfmRdaServer( app )
    app.router.add_get('/aiohttp/test', srv.testGetHandler)
    web.run_app(app, path = srv.conf.get( 'files', 'server_socket' ) )
