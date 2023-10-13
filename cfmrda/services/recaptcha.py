#!/usr/bin/python
#coding=utf-8
import logging

import aiohttp

from cfmrda.common import site_conf

async def check_recaptcha(response):
    conf = site_conf()
    try:
        rc_data = {'secret': conf.get('recaptcha', 'secret'),\
                'response': response}
        async with aiohttp.ClientSession() as session:
            resp = await session.post(conf.get('recaptcha', 'verifyURL'),\
                data=rc_data)
            resp_data = await resp.json()
            return resp_data['success']
    except Exception:
        logging.exception('Recaptcha error')
        return False
