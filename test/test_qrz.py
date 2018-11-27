#!/usr/bin/python3
#coding=utf-8
import logging
import asyncio

import pytest

from qrz import QRZComLink

@pytest.fixture(scope="session")
def qrz_com_link():
    return QRZComLink(asyncio.get_event_loop())

def test_qcl_get_data(qrz_com_link):
    logging.warning('test qrz.com query')
    data = qrz_com_link.get_data('R9LM')
    logging.debug( data )
    assert data['email']
    logging.debug(data['email'])


