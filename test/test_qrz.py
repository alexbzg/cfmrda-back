#!/usr/bin/python3
#coding=utf-8
import logging
import asyncio
import sys

import pytest

sys.path.append('cfmrda')
from qrz import QRZComLink, QRZRuLink
from common import appRoot

logging.basicConfig( level = logging.DEBUG,
        format='%(asctime)s %(message)s', 
        datefmt='%Y-%m-%d %H:%M:%S' )
logging.info( 'starting qrz tests' )

@pytest.fixture(scope="session")
def qrz_com_link():
    return QRZComLink(asyncio.get_event_loop())

@pytest.fixture(scope="session")
def qrz_ru_link():
    return QRZRuLink(asyncio.get_event_loop())

def test_qcl_get_data(qrz_com_link):
    logging.warning('test qrz.com query')
    data = qrz_com_link.get_data('R7CL')
    assert data['email'] == 'welcome@masterslav.ru'
    logging.warning( data )

def test_qrl_get_data(qrz_ru_link):
    logging.warning('test qrz.ru query')
    loop = asyncio.get_event_loop()
    answer = asyncio.Event(loop=loop)

    def data_cb(data):
        logging.warning(data)
        assert data['email'] == 'welcome@masterslav.ru'
        answer.set()
        assert 0

    @asyncio.coroutine
    def do_test():
        req = {'cs': 'R7CL', 'cb': data_cb}
        yield from qrz_ru_link.cs_queue.put(req)
        yield from answer.wait()

    loop.run_until_complete(do_test())

