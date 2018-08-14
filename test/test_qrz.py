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

def test_qcl_get_data(qrz_com_link):
    logging.warning('test qrz.com query')
    data = qrz_com_link.get_data('R7CL')
    logging.debug( data )
    assert data['email'] == 'welcome@masterslav.ru'


