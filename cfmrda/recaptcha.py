#!/usr/bin/python
#coding=utf-8

import asyncio, aiohttp, logging
from common import siteConf

@asyncio.coroutine
def checkRecaptcha( response ):
    conf = siteConf()
    try:
        rcData = { 'secret': conf.get( 'recaptcha', 'secret' ),\
                'response': response }
        with aiohttp.ClientSession() as session:
            resp = yield from session.post( \
                    conf.get( 'recaptcha', 'verifyURL' ), data = rcData )
            respData = yield from resp.json()
            return respData['success']
    except Exception:
        logging.exception( 'Recaptcha error' )
        return False

