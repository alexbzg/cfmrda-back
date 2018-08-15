#!/usr/bin/python
#coding=utf-8

import asyncio
import logging

import aiohttp

from common import site_conf

@asyncio.coroutine
def check_recaptcha(response):
    conf = site_conf()
    try:
        rc_data = {'secret': conf.get('recaptcha', 'secret'),\
                'response': response}
        with aiohttp.ClientSession() as session:
            resp = yield from session.post(conf.get('recaptcha', 'verifyURL'),\
                data=rc_data)
            resp_data = yield from resp.json()
            return resp_data['success']
    except Exception:
        logging.exception('Recaptcha error')
        return False

