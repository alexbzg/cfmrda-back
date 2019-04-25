#!/usr/bin/python3
#coding=utf-8

import os
import logging
import json
import asyncio

import requests
import xmltodict

from common import site_conf

class QRZComLink:

    def __init__(self, loop):
        conf = site_conf()
        self.loop = loop
        self.login = conf.get('QRZCom', 'login')
        self.password = conf.get('QRZCom', 'password')
        self.session_id = None
        self.get_session_id()

    def get_session_id(self):
        conf = site_conf()
        fp_session = conf.get('QRZCom', 'session_file')
        if os.path.isfile(fp_session):
            with open(fp_session, 'r') as f_session:
                session_id = f_session.read()
                if self.session_id != session_id:
                    self.session_id = session_id
                    return

        req, r_body = None, None
        try:
            req = requests.get('http://xmldata.qrz.com/xml/current/?username=' \
                    + self.login + ';password=' + self.password)
            r_body = req.text
            req.raise_for_status()
            r_dict = xmltodict.parse(r_body)
            if 'Key' in r_dict['QRZDatabase']['Session']:
                self.session_id = r_dict['QRZDatabase']['Session']['Key']
                with open(fp_session, 'w') as f_session:
                    f_session.write(self.session_id)
            else:
                raise Exception('Wrong QRZ response')
        except Exception:
            logging.exception('Error logging into QRZ.com')
            if req:
                logging.error('Http result code: ' + str(req.status_code()))
                logging.error('Http response body: ' + req.text)
            self.loop.call_later(60*10, self.get_session_id)

    def get_data(self, callsign, bio=False):
        if self.session_id:
            req, r_body = None, None
            data_type = 'html' if bio else 'callsign'
            try:
                req = requests.get('http://xmldata.qrz.com/xml/current/?s=' \
                        + self.session_id + ';' + data_type + '=' + callsign)
                r_body = req.text
                req.raise_for_status()
                if bio:
                    return r_body
                r_dict = xmltodict.parse(r_body)
                if 'Callsign' in r_dict['QRZDatabase']:
                    return r_dict['QRZDatabase']['Callsign']
                elif 'Session' in r_dict['QRZDatabase'] and \
                    'Error' in r_dict['QRZDatabase']['Session'] and \
                    (r_dict['QRZDatabase']['Session']['Error'] == \
                    'Session Timeout' or \
                    r_dict['QRZDatabase']['Session']['Error'] == \
                    'Invalid session key'):
                    self.get_session_id()
                    if self.session_id:
                        return self.get_data(callsign)
                elif 'Session' in r_dict['QRZDatabase'] and \
                    'Error' in r_dict['QRZDatabase']['Session']:
                    if 'Not found' in r_dict['QRZDatabase']['Session']['Error']:
                        return None
                    else:
                        raise Exception('QRZ error: ' + \
                            r_dict['QRZDatabase']['Session']['Error'])
                else:
                    raise Exception('Wrong QRZ response: ' + json.dumps(r_dict))
            except Exception:
                logging.exception('Error querying QRZ.com')
                if req:
                    logging.error('Http result code: ' + str(req.status_code()))
                    logging.error('Http response body: ' + r_body)
                return None
        else:
            self.get_session_id()
            if self.session_id:
                return self.get_data(callsign)


class QRZRuLink:

    def __init__(self, loop):
        conf = site_conf()
        self.loop = loop
        self.login = conf.get('QRZRu', 'login')
        self.password = conf.get('QRZRu', 'password')
        self._query_interval = conf.getfloat('QRZRu', 'query_interval')
        self._session_interval_success = \
            conf.getint('QRZRu', 'session_interval_success')
        self.session_interval_failure = \
            conf.getint('QRZRu', 'session_interval_failure')
        self.cs_queue = asyncio.Queue()
        self.session_task = None
        self.queue_task = None

        self.get_session_id()

    @asyncio.coroutine
    def do_queue_task(self):
        while True:
            queue_item = yield from self.cs_queue.get()
            queue_item['cb'](self.get_data(queue_item['cs']))
            yield from asyncio.sleep(self._query_interval)

    def start_queue_task(self):
        self.stop_queue_task()
        self.queue_task = asyncio.async(self.do_queue_task())

    def stop_queue_task(self):
        if self.queue_task:
            self.queue_task.cancel()
            self.queue_task = None

    def get_session_id(self):
        if self.queue_task:
            self.stop_queue_task()
            self.session_id = None
            self.session_task = self.loop.call_later(self._query_interval, self.get_session_id)
            return
        if self.session_task:
            self.session_task.cancel()
            self.session_task = None
        req, r_body = None, None
        try:
            req = requests.get('http://api.qrz.ru/login?u=' + \
                    self.login + '&p=' + self.password)
            r_body = req.text
            req.raise_for_status()
            r_dict = xmltodict.parse(r_body)
            if 'session_id' in r_dict['QRZDatabase']['Session']:
                self.session_id = r_dict['QRZDatabase']['Session']['session_id']
                self.start_queue_task()
                self.session_task = \
                    self.loop.call_later(self._session_interval_success,\
                    self.get_session_id)
                logging.debug('New qrz.ru session id:' + self.session_id)
            else:
                if 'error' in r_dict['QRZDatabase']['Session']:
                    logging.error('QRZ returned error: ' + \
                            r_dict['QRZDatabase']['Session']['error'])
                    self.session_task = \
                        self.loop.call_later(self.session_interval_failure,\
                        self.get_session_id)
                else:
                    raise Exception('Wrong QRZ response')
        except Exception:
            logging.exception('Error getting logging into QRZ')
            if req:
                logging.error('Http result code: ' + str(req.status_code))
                logging.error('Http response body: ' + r_body)
            self.session_task = \
                self.loop.call_later(self.session_interval_failure,\
                    self.get_session_id)

    @asyncio.coroutine
    def query(self, callsign):
        _complete = asyncio.Event(loop=self.loop)
        _data = None

        def callback(data):
            nonlocal _data
            _data = data
            _complete.set()

        yield from self.cs_queue.put({'cs': callsign, 'cb': callback})
        yield from _complete.wait()
        return _data

    def get_data(self, callsign):
        if self.session_id:
            req, r_body = None, None
            try:
                req = requests.get('http://api.qrz.ru/callsign?id=' + \
                        self.session_id + '&callsign=' + callsign)
                r_body = req.text
                r_dict = xmltodict.parse(r_body)
                if 'Callsign' in r_dict['QRZDatabase']:
                    return r_dict['QRZDatabase']['Callsign']
                else:
                    raise Exception('Wrong QRZ response')
            except Exception:
                if req:
                    if req.status_code == 404:
                        return None
                    elif req.status_code == 403:
                        self.get_session_id()
                        return self.get_data(callsign)
                logging.exception('QRZ query error')
                if req:
                    logging.error('Http result code: ' + str(req.status_code))
                    logging.error('Http response body: ' + r_body)
                return None
        else:
            self.get_session_id()
            return self.get_data(callsign)

