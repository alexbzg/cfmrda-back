#!/usr/bin/python3
#coding=utf-8

import asyncio
import logging
import time
import base64
import re
import os
import string
import random
import csv
import io
from datetime import datetime, timedelta

from aiohttp import web
import jwt
import chardet
import requests

from common import site_conf, start_logging, APP_ROOT, datetime_format, date_format
from db import DBConn, typed_values_list, CfmrdaDbException, params_str, splice_params
import send_email
from secret import get_secret, create_token
import recaptcha
from json_utils import load_json, save_json, JSONvalidator
from qrz import QRZComLink, QRZRuLink
from ham_radio import load_adif, strip_callsign, ADIFParseException
from ext_logger import ExtLogger, ExtLoggerException

CONF = site_conf()
start_logging('srv', level=CONF.get('logs', 'srv_level'))
logging.debug("restart")

def _del_qsl_image(qsl_id):
    qsl_dir = CONF.get('web', 'root') + '/qsl_images/'
    pattern = '^' + str(qsl_id) + '_.*$'
    for file in os.listdir(qsl_dir):
        if re.search(pattern, file):
            os.remove(os.path.join(qsl_dir, file))


class CfmRdaServer():

    @staticmethod
    def response_error_default():
        return web.HTTPBadRequest(\
            text='Ошибка сайта. Пожалуйста, попробуйте позднее.')

    @staticmethod
    def response_error_recaptcha():
        return web.HTTPBadRequest(text='Проверка на робота не пройдена ' +\
            'или данные устарели. Попробуйте еще раз.')

    @staticmethod
    def response_ok():
        return web.Response(text='OK')

    @staticmethod
    def response_error_email_cfm():
        return web.HTTPBadRequest(text='Ваш адрес электронной почты не подтвержден.')

    @staticmethod
    def response_error_admin_required():
        return web.HTTPBadRequest(text='Необходимы права администратора сайта.')

    def __init__(self, loop):
        self._loop = loop
        self._db = DBConn(CONF.items('db'))
        self._qrzcom = QRZComLink(loop)
        if CONF.has_option('QRZRu', 'login'):
            self._qrzru = QRZRuLink(loop)
        asyncio.async(self._db.connect())
        self._secret = get_secret(CONF.get('files', 'secret'))
        self._site_admins = str(CONF.get('web', 'admins')).split(' ')
        self._json_validator = JSONvalidator(\
            load_json(APP_ROOT + '/schemas.json'))

    def is_admin(self, callsign):
        return callsign in self._site_admins

    def create_token(self, data):
        return create_token(self._secret, data)

    @asyncio.coroutine
    def get_user_data(self, callsign):
        data = yield from self._db.get_object('users', \
                {'callsign': callsign}, False, True)
        if data:
            data['oldCallsigns'] = {}
            data['oldCallsigns']['confirmed'] = yield from\
                self._db.get_old_callsigns(callsign, confirmed=True)
            data['oldCallsigns']['all'] = yield from\
                self._db.get_old_callsigns(callsign)
            for type in data['oldCallsigns']:
                if not data['oldCallsigns'][type]:
                    data['oldCallsigns'][type] = []
            data['newCallsign'] = yield from self._db.get_new_callsign(callsign)
        return data

    @asyncio.coroutine
    def login_hndlr(self, request):
        data = yield from request.json()
        if 'mode' in data:
            if data['mode'] == 'register':
                return (yield from self.register_user(data))
            elif data['mode'] == 'login':
                return (yield from self.login(data))
            elif data['mode'] == 'passwordRequest':
                return (yield from self.password_request(data))
            elif data['mode'] == 'passwordChange':
                return (yield from self.password_change(data))
            elif data['mode'] == 'emailRequest':
                return (yield from self.email_request(data))
        logging.debug(data)
        return CfmRdaServer.response_error_default()

    @asyncio.coroutine
    def correspondent_email_hndlr(self, request):
        callsign = request.match_info.get('callsign', None)
        response = {'email': None, 'reason': None}
        blacklist_check = yield from self._db.execute("""
            select * from cfm_request_blacklist
            where callsign = %(callsign)s""",\
            {'callsign': callsign}, False)
        if blacklist_check:
            response['reason'] = 'blacklist'
        else:
            qrz_data = self._qrzcom.get_data(callsign)
            if qrz_data and 'email' in qrz_data and qrz_data['email']:
                response['email'] = qrz_data['email']
            else:
                response['reason'] = 'not found'
        return web.json_response(response)

    @asyncio.coroutine
    def cfm_request_qso_hndlr(self, request):
        data = yield from request.json()
        callsign = self.decode_token(data)
        if not isinstance(callsign, str):
            return callsign
        if 'qso' in data:
            errors = []
            if self._json_validator.validate('cfmRequestQso', data):
                user_data = yield from self.get_user_data(callsign)
                email = user_data['email']
                for qso in data['qso']:
                    qso['hunterEmail'] = email
                    qso['tstamp'] = (qso['date'].split('T'))[0] + ' ' +\
                        qso['time']
                    qso['user_cs'] = callsign
                    try:
                        if not (yield from self._db.execute("""
                            insert into cfm_request_qso 
                            (correspondent, callsign, station_callsign, rda,
                            band, mode, tstamp, hunter_email, user_cs,
                            correspondent_email, rec_rst, sent_rst)
                            values (%(correspondent)s, %(callsign)s, 
                            %(stationCallsign)s, %(rda)s, %(band)s, %(mode)s, 
                            %(tstamp)s, %(hunterEmail)s, %(user_cs)s, %(email)s,
                            %(recRST)s, %(sentRST)s)""", qso, False)):
                            errors.append(\
                                {'qso':qso,\
                                'error': 'Ошибка сервера. Server error.'})
                    except CfmrdaDbException as exc:
                        errors.append({'qso': qso,\
                            'error': str(exc)})
                return web.json_response(errors)
            else:
                return web.Response(text="OK")
        else:
            if callsign:
                if 'delete' in data and data['delete']:
                    check_state = yield from self._db.execute("""
                        select sent
                        from cfm_request_qso 
                        where id = %(id)s""", {'id': data['delete']})
                    sql = """delete from cfm_request_qso
                        where id = %(id)s""" if check_state is None\
                        else """update cfm_request_qso
                            set user_cs = null
                            where id = %(id)s"""
                    if (yield from self._db.execute(sql, {'id': data['delete']})):
                        return CfmRdaServer.response_ok()
                    else:
                        return CfmRdaServer.response_error_default()
                else:
                    qso = yield from self._db.execute("""
                        select json_build_object(
                        'id', id,
                        'callsign', callsign,
                        'state', state, 'viewed', viewed, 'sent', sent,
                        'comment', comment,
                        'blacklist',
                        exists (select from cfm_request_blacklist
                            where cfm_request_blacklist.callsign = correspondent),
                        'stationCallsign', station_callsign, 'rda', rda, 
                        'band', band, 'mode', mode, 
                        'statusDate', to_char(status_tstamp, 'DD Month YYYY'),
                        'date', to_char(tstamp, 'DD Month YYYY'),
                        'time', to_char(tstamp, 'HH24:MI'),
                        'rcvRST', rec_rst, 'sntRST', sent_rst)
                            from cfm_request_qso
                            where user_cs = %(callsign)s
                        """, {'callsign': callsign}, True)
                    if not qso:
                        qso = []
                    return web.json_response(qso)
            else:
                return CfmRdaServer.response_error_default()

    @asyncio.coroutine
    def contact_support_hndlr(self, request):
        data = yield from request.json()
        if self._json_validator.validate('contactSupport', data):
            email = None
            callsign = None
            if 'token' in data:
                callsign = self.decode_token(data)
                if isinstance(callsign, str):
                    user_data = yield from self.get_user_data(callsign)
                    email = user_data['email']
                else:
                    return callsign
            else:
                rc_test = yield from recaptcha.check_recaptcha(data['recaptcha'])
                if not rc_test:
                    return CfmRdaServer.response_error_recaptcha()
                email = data['email']
            send_email.send_email(text=data['text'],\
                to=CONF.get('email', 'address'),\
                fr=email,\
                subject="CFMRDA.ru support" + \
                    (' (' + callsign + ')' if callsign else ''))
            return CfmRdaServer.response_ok()

        return CfmRdaServer.response_error_default()

    @asyncio.coroutine
    def chat_hndlr(self, request):
        data = yield from request.json()
        if self._json_validator.validate('chat', data):
            callsign = None
            admin = False
            site_root = CONF.get('web', 'root')
            if 'token' in data:
                callsign = self.decode_token(data)
                if isinstance(callsign, str):
                    admin = self.is_admin(callsign)
                else:
                    return callsign
            else:
                callsign = data['callsign']
            if 'message' or 'delete' in data:
                chat_path = site_root + '/json/chat.json'
                chat = load_json(chat_path)
                if not chat:
                    chat = []
                if 'delete' in data:
                    if not admin:
                        return web.HTTPBadRequest(\
                            text='Только адмнистраторы могут удалять сообщения')
                    chat = [x for x in chat if x['ts'] != data['delete']]
                if 'message' in data:
                    msg = {'callsign': callsign,\
                        'text': data['message'],\
                        'admin': admin,\
                        'ts': time.time()}
                    msg['date'], msg['time'] = datetime_format(datetime.utcnow())
                    if 'name' in data:
                        msg['name'] = data['name']
                    chat.insert(0, msg)
                    if len(chat) > 100:
                        chat = chat[:100]
                save_json(chat, chat_path)
            active_users_path = site_root + '/json/active_users.json'
            active_users = load_json(active_users_path)
            if not active_users:
                active_users = {}
            now = int(time.time())
            active_users = {k : v for k, v in active_users.items()\
                if now - v['ts'] < 120}
            if 'exit' in data and data['exit'] and callsign in active_users:
                del active_users[callsign]
            else:
                active_users[callsign] = {'ts': now, 'admin': admin}
                if 'typing' in data and data['typing']:
                    active_users[callsign]['typing'] = True
            save_json(active_users, active_users_path)
            return CfmRdaServer.response_ok()

        return CfmRdaServer.response_error_default()

    @asyncio.coroutine
    def email_request(self, data):
        callsign = self.decode_token(data)
        if isinstance(callsign, str):
            yield from self._db.param_update('users', {'callsign': callsign},\
                {'email_confirmed': True})
            return web.HTTPFound(CONF.get('web', 'address'))
        else:
            return callsign

    @asyncio.coroutine
    def _cfm_qsl_qso_new(self, callsign, data):
        if self._json_validator.validate('cfmQslQso', data['qso']):
            asyncio.async(self._load_qrz_rda(data['qso']['stationCallsign']))
            res = None
            try:
                res = yield from self._db.get_object('cfm_qsl_qso',\
                    {'user_cs': callsign,\
                    'station_callsign': data['qso']['stationCallsign'],\
                    'rda': data['qso']['rda'],\
                    'tstamp': data['qso']['date'].split('T')[0] + ' ' +\
                        data['qso']['time'],\
                    'band': data['qso']['band'],\
                    'mode': data['qso']['mode'],\
                    'callsign': data['qso']['callsign'],\
                    'new_callsign': data['qso']['newCallsign']\
                        if 'newCallsign' in data['qso'] else None,\
                    'image': data['qso']['image']['name']}, True)
            except CfmrdaDbException as exc:
                return web.HTTPBadRequest(text=str(exc))
            if res:
                image_bytes = \
                    base64.b64decode(\
                        data['qso']['image']['file'].split(',')[1])
                with open(CONF.get('web', 'root') +\
                    '/qsl_images/' + str(res['id']) + '_' +\
                    data['qso']['image']['name'], 'wb') as image_file:
                    image_file.write(image_bytes)
            else:
                return CfmRdaServer.response_error_default()
            return CfmRdaServer.response_ok()
        else:
            return CfmRdaServer.response_error_default()


    @asyncio.coroutine
    def _cfm_qsl_qso_delete(self, callsign, data):
        res = yield from self._db.param_delete('cfm_qsl_qso',\
            {'id': data['delete'], 'user_cs': callsign})
        if res:
            _del_qsl_image(res['id'])
            return CfmRdaServer.response_ok()
        else:
            return CfmRdaServer.response_error_default()

    @asyncio.coroutine
    def _get_qsl_list(self, callsign=None):
        sql = """
            select json_agg(json_build_object(
                'id', id,
                'callsign', callsign,""" +\
                ('' if callsign else """'callsignRda',
                (select json_agg(distinct rda)
                    from callsigns_rda 
                    where callsigns_rda.callsign = station_callsign and
                        (dt_start is null or dt_start <= tstamp) and
                        (dt_stop is null or dt_stop >= date(tstamp))
                    ),""") + """
                'stationCallsign', station_callsign,
                'rda', rda,
                'band', band,
                'mode', mode,
                'newCallsign', new_callsign,
                'date', to_char(tstamp, 'DD mon YYYY'),
                'time', to_char(tstamp, 'HH24:MI'),
                'state', state,
                'admin', admin,
                'comment', comment,
                'image', image))
            from cfm_qsl_qso 
            where """
        if callsign:
            sql += "user_cs = %(callsign)s"
        else:
            sql += "state is null"
        logging.debug(sql)
        qsl_list = yield from self._db.execute(sql, {'callsign': callsign})
        logging.debug(qsl_list)
        if not qsl_list:
            qsl_list = []
        return qsl_list

    @asyncio.coroutine
    def cfm_qsl_qso_hndlr(self, request):
        data = yield from request.json()
        callsign = self.decode_token(data)
        if isinstance(callsign, str):
            user_data = yield from self.get_user_data(callsign)
            if user_data['email_confirmed']:
                if 'qso' in data:
                    return (yield from self._cfm_qsl_qso_new(callsign, data))
                elif 'delete' in data:
                    return (yield from self._cfm_qsl_qso_delete(callsign, data))
                else:
                    qsl_list = yield from self._get_qsl_list(callsign)
                    return web.json_response(qsl_list)
            else:
                return CfmRdaServer.response_error_email_cfm()
        else:
            return callsign

    @asyncio.coroutine
    def qsl_admin_hndlr(self, request):
        data = yield from request.json()
        callsign = self.decode_token(data)
        if isinstance(callsign, str):
            if self.is_admin(callsign):
                if 'qsl' in data:
                    if self._json_validator.validate('qslAdmin', data['qsl']):
                        for qso in data['qsl']:
                            qso['admin'] = callsign
                        if (yield from self._db.execute("""
                            update cfm_qsl_qso 
                            set state = %(state)s, comment = %(comment)s,
                            admin = %(admin)s
                            where id = %(id)s""", data['qsl'])):
                            for qsl in data['qsl']:
                                _del_qsl_image(qsl['id'])
                            return CfmRdaServer.response_ok()
                        else:
                            return CfmRdaServer.response_error_default()
                    else:
                        return CfmRdaServer.response_error_default()
                else:
                    qsl_list = yield from self._get_qsl_list()
                    return web.json_response(qsl_list)
            else:
                return CfmRdaServer.response_error_admin_required()
        else:
            return callsign


    @asyncio.coroutine
    def adif_hndlr(self, request):
        data = yield from request.json()
        if self._json_validator.validate('adif', data):
            callsign = self.decode_token(data)
            if isinstance(callsign, str):
                user_data = yield from self.get_user_data(callsign)
                if user_data['email_confirmed']:
                    station_callsign_field = None
                    station_callsign = None
                    rda_field = None
                    activators = set([])
                    response = []
                    if data['stationCallsignFieldEnable']:
                        station_callsign_field = data['stationCallsignField']
                    else:
                        station_callsign = data['stationCallsign']
                        activators.add(station_callsign)
                    if data['rdaFieldEnable']:
                        rda_field = data['rdaField']
                    if 'additionalActivators' in data and\
                        data['additionalActivators']:
                        for act_cs in re.split(r"(?:\s|,|;)",\
                            data["additionalActivators"]):
                            activator = strip_callsign(act_cs)
                            if activator:
                                activators.add(activator)
                    for file in data['files']:

                        adif_bytes = \
                            base64.b64decode(file['file'].split(',')[1])
                        file_hash = yield from self._db.check_upload_hash(adif_bytes)
                        if not file_hash:
                            response.append({'file': file['name'],\
                                'message': 'Файл уже загружен'})
                            continue

                        adif_enc = chardet.detect(adif_bytes)
                        adif = adif_bytes.decode(adif_enc['encoding'], 'ignore')
                        try:
                            adif_data = load_adif(adif, \
                                station_callsign_field=station_callsign_field,\
                                rda_field=rda_field)
                            logging.debug('ADIF parsed')
                        except ADIFParseException as exc:
                            response.append({'file': file['name'],\
                                'message': str(exc)})
                            continue
                        if not adif_data['qso']:
                            response.append({\
                                'file': file['name'],\
                                'message' : 'Не найдено корректных qso. No valid qso were found.',\
                                'qso': {\
                                    'ok': 0,
                                    'error': adif_data['qso_errors_count'],\
                                    'errors': adif_data['qso_errors']}\
                            })

                        for qso in adif_data['qso']:
                            qso['station_callsign'] = station_callsign or\
                                qso['station_callsign']
                            qso['rda'] = qso['rda'] if rda_field else file['rda']

                        db_res = yield from self._db.create_upload(\
                            callsign=callsign,\
                            date_start=adif_data['date_start'],\
                            date_end=adif_data['date_end'],\
                            file_hash=file_hash,\
                            activators=activators |\
                                (set([adif_data['activator']]) if adif_data['activator']\
                                else set([])),
                            qsos=adif_data['qso'])
                        db_res['file'] = file['name']
                        if not rda_field:
                            db_res['rda'] = file['rda']
                        db_res['message'] = adif_data['message'] + \
                            (' ' if adif_data['message'] and db_res['message'] else '') + \
                            db_res['message']
                        db_res['qso']['error'] += adif_data['qso_errors_count']
                        db_res['qso']['errors'].update(adif_data['qso_errors'])
                        response.append(db_res)

                    logging.debug(response)
                    return web.json_response(response)
                else:
                    return web.HTTPBadRequest(text='Ваш адрес электронной почты не подтвержден.')
            else:
                return callsign
        else:
            return CfmRdaServer.response_error_default()

    @asyncio.coroutine
    def password_request(self, data):
        error = None
        if self._json_validator.validate('passwordRequest', data):
            rc_test = yield from recaptcha.check_recaptcha(data['recaptcha'])
            if rc_test:
                user_data = yield from self.get_user_data(data['callsign'])
                if user_data:
                    token = self.create_token(\
                        {'callsign': data['callsign'], 'time': time.time()})
                    text = """Пройдите по ссылкe, чтобы сменить пароль на CFMRDA.ru:

""" \
                        + CONF.get('web', 'address')\
                        + '/#/login?token=' + token + """

Если вы не запрашивали смену пароля на CFMRDA.ru, просто игнорируйте это письмо.
Ссылка будет действительна в течение 1 часа.

Служба поддержки CFMRDA.ru"""
                    send_email.send_email(text=text,\
                        fr=CONF.get('email', 'address'),\
                        to=user_data['email'],\
                        subject="CFMRDA.ru - смена пароля")
                else:
                    error =\
                        'Позывной не зарегистрирован на CFMRDA.ru'
            else:
                error = 'Проверка на робота не пройдена или данные устарели. Попробуйте еще раз.'
        else:
            return CfmRdaServer.response_error_default()
        if error:
            return web.HTTPBadRequest(text=error)
        else:
            return CfmRdaServer.response_ok()

    @asyncio.coroutine
    def password_change(self, data):
        if self._json_validator.validate('passwordChange', data):
            callsign = self.decode_token(data, check_time=True)
            if isinstance(callsign, str):
                yield from self._db.param_update('users', {'callsign': callsign},\
                    {'email_confirmed': True, 'password': data['password']})
                return CfmRdaServer.response_ok()
            else:
                return callsign
        else:
            return CfmRdaServer.response_error_default()

    @asyncio.coroutine
    def _edit_uploads(self, data, callsign):
        if 'delete' in data:
            if not self.is_admin(callsign):
                check_uploader = yield from self._db.execute("""
                    select user_cs 
                    from uploads 
                    where id = %(id)s
                    """, data, False)
                if check_uploader != callsign:
                    return CfmRdaServer.response_error_default()

            upload_data = yield from self._db.execute("""
                select json_build_object('activators', activators,
                    'rda', rda, 'qso', qsos,
                    'delDate', to_char(now(), 'DD mon YYYY'),
                    'delTime', to_char(now(), 'HH24:MI'),
                    'uploadType', upload_type,
                    'uploader', uploader, 
                    'upload_ts', to_char(tstamp, 'DD MM YYYY HH24:MI:SS')) as data
                from
                (select user_cs as uploader, upload_type, tstamp
                    from uploads            
                    where id = %(id)s) as u,
                lateral 
                (select array_agg(distinct station_callsign) as activators 
                    from qso 
                    where upload_id = %(id)s) as acts,
                lateral 
                (select array_agg(distinct rda) as rda   
                    from qso 
                    where upload_id = %(id)s) as rdas, 
                lateral
                (select count(*) as qsos
                    from qso
                    where upload_id = %(id)s) as qsos
                """, data, False)
            upload_data['delBy'] = callsign

            if not (yield from self._db.execute("""
                delete from qso where upload_id = %(id)s
                """, data)):
                return CfmRdaServer.response_error_default()
            if not (yield from self._db.execute("""
                delete from activators where upload_id = %(id)s
                """, data)):
                return CfmRdaServer.response_error_default()
            if not (yield from self._db.execute("""
                delete from uploads where id = %(id)s
                """, data)):
                return CfmRdaServer.response_error_default()
            if upload_data['rda'] and\
                datetime.now() - datetime.strptime(upload_data['upload_ts'], '%d %m %Y %H:%M:%S') >\
                timedelta(days=1):
                del_uploads_path = CONF.get('web', 'root') + '/json/del_uploads.json'
                del_uploads = load_json(del_uploads_path) or []
                del_uploads.insert(0, upload_data)
                if len(del_uploads) > 20:
                    del_uploads = del_uploads[:20]
                save_json(del_uploads, del_uploads_path)
        elif 'enabled' in data:
            if callsign not in self._site_admins:
                return CfmRdaServer.response_error_default()
            if not(yield from self._db.execute("""
                update uploads set enabled = %(enabled)s where id = %(id)s
                """, data)):
                return CfmRdaServer.response_error_default()
        return CfmRdaServer.response_ok()

    @asyncio.coroutine
    def cfm_blacklist_hndlr(self, request):
        data = yield from request.json()
        callsign = self.decode_token(data)
        bl_callsign = None
        if isinstance(callsign, str):
            if 'admin' in data:
                if self.is_admin(callsign):
                    bl_callsign = data['blacklist']
                else:
                    return CfmRdaServer.response_error_admin_required()
            else:
                bl_callsign = callsign
            if (yield from self._db.cfm_blacklist(bl_callsign)):
                return CfmRdaServer.response_ok()
            else:
                return CfmRdaServer.response_error_default()
        else:
            return callsign

    @asyncio.coroutine
    def ann_hndlr(self, callsign, data):
        site_root = CONF.get('web', 'root')
        ann_path = site_root + '/json/ann.json'
        ann = load_json(ann_path)
        if not ann:
            ann = []
        if 'new' in data:
            _ts = time.time()
            data['new']['callsign'] = callsign
            data['new']['ts'] = _ts
            data['new']['date'] = date_format(datetime.utcnow())
            ann.insert(0, data['new'])
        if 'delete' in data:
            callsign = self._require_callsign(data, True)
            if not isinstance(callsign, str):
                return callsign
            ann = [x for x in ann if x['ts'] != data['delete']]
        save_json(ann, ann_path)
        return CfmRdaServer.response_ok()

    @asyncio.coroutine
    def _ext_loggers_update(self, callsign, update):
        """stores ext_logger record in db
        update parameter format:
        {id (null or absent if new record), logger, loginData}
        response format:
        {id, state: 0 if login was succefull else 1} if success else
        statndard error response
        """
        logger_type = update['logger']
        logger_params = ExtLogger.types[logger_type]
        schema = logger_params['schema'] if 'schema' in logger_params\
            else 'extLoggersLoginDefault'
        if not self._json_validator.validate(schema, update['loginData']):
            return CfmRdaServer.response_error_default()
        logger = ExtLogger(update['logger'])
        login_check = False
        try:
            logger.login(update['loginData'])
            login_check = True
        except (requests.exceptions.HTTPError, ExtLoggerException) as ext:
            logging.exception(ext)
        params = splice_params(update,\
            ['logger', 'loginData', 'id'])
        params['state'] = 0 if login_check else 1
        params['callsign'] = callsign
        sql = ""
        _id = None
        if 'id' in params and params['id']:
            sql = """update ext_loggers
                set login_data = %(loginData)s, state = %(state)s, logger = %(logger)s 
                where id = %(id)s and callsign=%(callsign)s;"""
            _id = params['id']
        else:
            sql = """insert into ext_loggers (callsign, logger, login_data, state)
                select %(callsign)s, %(logger)s, %(loginData)s, %(state)s
                returning id"""
        db_res = yield from self._db.execute(sql, params)
        if db_res:
            if not _id:
                _id = db_res
            return web.json_response({'state': params['state'], 'id': _id})
        else:
            return CfmRdaServer.response_error_default()

    @asyncio.coroutine
    def _ext_loggers_delete(self, callsign, delete):
        """deletes ext_logger record from db return standard ok/error responses"""
        params = {'id': delete, 'callsign': callsign}
        uploads = yield from self._db.execute("""select id as uid from uploads 
            where ext_logger_id = %(id)s and user_cs = %(callsign)s""", params, True)
        if uploads:
            for id in uploads:
                yield from self._db.remove_upload(id)
        db_res = yield from self._db.execute("""delete from ext_loggers
            where id = %(id)s and callsign = %(callsign)s
            returning id""", {'id': delete, 'callsign': callsign})
        if db_res and db_res == delete:
            return CfmRdaServer.response_ok()
        else:
            return CfmRdaServer.response_error_default()

    @asyncio.coroutine
    def ext_loggers_hndlr(self, callsign, data):
        """handles loggers request
        when data has no fields 'update' or 'delete'
        returns
        {'loggers': dict with supported loggers
            {logger-name: {'loginDataFields': [list of fields in login request
                to logger],
                'schema': name of valdation schema for login data
            }},
            'accounts': array of user's logger accounts
            [{'id', 'logger', 'loginData', 'state', 'lastUpdated', 'qsoCount'}]
            }
        """
        if 'update' in data:
            return (yield from self._ext_loggers_update(callsign, data['update']))
        elif 'delete' in data:
            return (yield from self._ext_loggers_delete(callsign, data['delete']))
        else:
            loggers = {}
            for (name, tmplt) in ExtLogger.types.items():
                logger = dict(tmplt)
                if 'loginDataFields' not in logger:
                    logger['loginDataFields'] = ExtLogger.default_login_data_fields
                if 'schema' not in logger:
                    logger['schema'] = 'extLoggersLoginDefault'
                loggers[name] = logger
            accounts = yield from self._db.execute("""
                select json_build_object('id', id,
                    'logger', logger, 
                    'loginData', login_data, 
                    'state', state,
                    'lastUpdated', to_char(last_updated, 'YYYY-MM-DD'), 
                    'qsoCount', qso_count)
                from ext_loggers
                    where callsign = %(callsign)s""", {'callsign': callsign}, True)
            if not accounts:
                accounts = []

            return web.json_response({'loggers': loggers, 'accounts': accounts})

    @asyncio.coroutine
    def callsigns_rda_hndlr(self, callsign, data):
        rsp = {}
        if 'delete' in data or 'new' in data or 'conflict' in data:
            callsign = self._require_callsign(data, True)
            if not isinstance(callsign, str):
                return callsign
            db_rslt = False
            if 'conflict' in data:
                db_rslt = yield from self._db.execute("""
                    select distinct cr0.callsign 
                    from callsigns_rda as cr0 join callsigns_rda as cr1 on
                        cr0.callsign = cr1.callsign and cr0.rda <> cr1.rda and
                        cr0.rda <> '***' and cr1.rda <> '***' and
                        cr0.dt_stop is null and cr1.dt_stop is null and 
                        cr1.id > cr0.id
                    order by cr0.callsign""", {}, True)
                return web.json_response(db_rslt)
            else:
                if 'delete' in data:
                    db_rslt = yield from self._db.execute("""
                        delete from callsigns_rda where id = %(delete)s""",\
                        data)
                else:
                    data['new']['source'] = callsign
                    data['new']['callsign'] = data['callsign']
                    db_rslt = yield from self._db.execute("""
                        insert into callsigns_rda
                        (callsign, dt_start, dt_stop, source, rda, comment)
                        values (%(callsign)s, %(dtStart)s, %(dtStop)s,
                            %(source)s, %(rda)s, %(comment)s)""", data['new'])
                if not db_rslt:
                    return CfmRdaServer.response_error_default()

        else:
            if 'callsign' in data:
                search = {'base': strip_callsign(data['callsign']),\
                        'selected': data['callsign']}
                if search['base']:
                    search['search'] = search['base'] + '/%'
                    rsp['suffixes'] = yield from self._db.execute("""
                        select distinct callsign 
                        from callsigns_rda
                        where callsign != %(selected)s and
                            (callsign like %(search)s or callsign = %(base)s)""",\
                        search, True)
        rsp['rdaRecords'] = yield from self._db.execute("""
            select id, source, rda, callsign, comment,
                to_char(ts, 'YYYY-MM-DD') as ts,
                case when dt_start is null and dt_stop is null then null
                    when dt_start is null and dt_stop is not null then
                        'till ' || to_char(dt_stop, 'DD mon YYYY')
                    when dt_stop is null and dt_start is not null then
                        'from ' || to_char(dt_start, 'DD mon YYYY')
                    else to_char(dt_start, 'DD mon YYYY') || ' - ' ||
                        to_char(dt_stop, 'DD mon YYYY')
                end as period
            from callsigns_rda where """ +\
            params_str(splice_params(data, ('callsign', 'rda')), ' and ') +\
            """
            order by dt_start desc
            """, data, True)
        return web.json_response(rsp)

    def _require_callsign(self, data, require_admin=False):
        callsign = self.decode_token(data)
        if isinstance(callsign, str):
            if require_admin:
                if not self.is_admin(callsign):
                    return CfmRdaServer.response_error_admin_required()
            return callsign
        else:
            return callsign

    def handler_wrap(self, handler, validation_scheme=None, require_callsign=True,\
        require_admin=False):

        @asyncio.coroutine
        def handler_wrapped(request):
            data = yield from request.json()
            if validation_scheme:
                if not self._json_validator.validate(validation_scheme, data):
                    return CfmRdaServer.response_error_default()
            callsign = None
            if require_callsign:
                callsign = self._require_callsign(data, require_admin)
                if not isinstance(callsign, str):
                    return callsign
            return (yield from handler(callsign, data))

        return handler_wrapped

    @asyncio.coroutine
    def old_callsigns_admin_hndlr(self, callsign, data):
        if 'confirm' in data:
            res = yield from self._db.set_old_callsigns(data['confirm']['new'],\
                data['confirm']['old'], True)
            if res:
                if res == 'OK':
                    return web.Response(text='OK')
                else:
                    return web.HTTPBadRequest(text=res)
            else:
                return CfmRdaServer.response_error_default()
        else:
            callsigns = yield from self._db.execute("""
                select new, 
                    array_agg(json_build_object('callsign', old, 
                        'confirmed', confirmed)) as old, 
                    bool_and(confirmed) as confirmed 
                from old_callsigns
                group by new""", keys=True)
            if not callsigns:
                callsigns = []
            return web.json_response(callsigns)

    @asyncio.coroutine
    def old_callsigns_hndlr(self, callsign, data):
        res = yield from self._db.set_old_callsigns(callsign, data['callsigns'])
        if res:
            return web.Response(text=res)
        else:
            return CfmRdaServer.response_error_default()

    @asyncio.coroutine
    def cfm_qso_hndlr(self, request):
        data = yield from request.json()
        logging.debug(data)
        callsign = self.decode_token(data)
        if isinstance(callsign, str):
            admin = False
            if 'admin' in data and data['admin']:
                admin_callsign = self.decode_token({'token': data['admin']})
                if isinstance(admin_callsign, str):
                    admin = self.is_admin(admin_callsign)
            if 'qso' in data:
                if 'cfm' in data['qso'] and data['qso']['cfm']:

                    upl_hash = yield from self._db.check_upload_hash(\
                            bytearray(repr(data['qso']['cfm']), 'utf8'))
                    if not upl_hash:
                        return CfmRdaServer.response_error_default()

                    ids = typed_values_list(data['qso']['cfm'], int)
                    date_start = yield from self._db.execute("""
                        select min(tstamp)
                        from cfm_request_qso
                        where id in """ + ids, None, False)
                    date_end = yield from self._db.execute("""
                        select max(tstamp)
                        from cfm_request_qso
                        where id in """ + ids, None, False)
                    qsos = yield from self._db.execute("""
                        select callsign, station_callsign, rda,
                            band, mode, tstamp 
                        from cfm_request_qso
                        where id in """ + ids, None, True)
                    yield from self._db.create_upload(\
                        callsign=callsign,\
                        date_start=date_start,\
                        date_end=date_end,\
                        file_hash=upl_hash,\
                        upload_type='email CFM',\
                        activators=[callsign],\
                        qsos=qsos)

                qso_sql = """
                    select hunter_email as email, 
                        json_agg(json_build_object(
                            'id', id,
                            'callsign', callsign, 
                            'stationCallsign', station_callsign, 'rda', rda, 
                            'band', band, 'mode', mode, 
                            'tstamp', to_char(tstamp, 'DD mon YYYY HH24:MI'),
                            'rcvRST', rec_rst, 'sntRST', sent_rst)
                        ) as qsos
                    from cfm_request_qso
                    where id in {ids} 
                    group by hunter_email"""
                qsos = {}
                for _type in data['qso']:
                    if data['qso'][_type]:
                        qsos_type = yield from self._db.execute(qso_sql.format(\
                            ids=typed_values_list(data['qso'][_type], int)),\
                             None, True)
                        for row in qsos_type:
                            if row['email'] not in qsos:
                                qsos[row['email']] = {}
                            qsos[row['email']][_type] = row['qsos']
                qso_params = []
                for _type in data['qso']:
                    state = _type == 'cfm'
                    for _id in data['qso'][_type]:
                        comment = data['comments'][str(_id)]\
                            if 'comments' in data and data['comments']\
                            and str(_id) in data['comments']\
                            else None
                        qso_params.append({'id': _id, 'comment': comment,\
                            'state': state})
                if qso_params:
                    logging.debug(qso_params)
                    if not (yield from self._db.execute("""update cfm_request_qso
                        set status_tstamp = now(), state = %(state)s, 
                            comment = %(comment)s
                        where id = %(id)s""", qso_params)):
                        return CfmRdaServer.response_error_default()
                if admin:
                    if 'blacklist' in data and data['blacklist']:
                        yield from self._db.cfm_blacklist(callsign)
                else:
                    test_callsign = yield from self.get_user_data(callsign)
                    if not test_callsign:
                        qrz_data = self._qrzcom.get_data(callsign)
                        if qrz_data and 'email' in qrz_data and qrz_data['email']:
                            email = qrz_data['email'].lower()
                            password = ''.join([\
                                random.choice(string.digits + string.ascii_letters)\
                                for _ in range(8)])
                            user_data = yield from self._db.get_object('users',\
                                {'callsign': callsign,\
                                'password': password,\
                                'email': email,\
                                'email_confirmed': True},\
                                True)
                            if user_data:
                                user_data['oldCallsigns'] = \
                                    {'confirmed': [], 'all': []}
                                user_data['newCallsign'] = yield from\
                                    self._db.get_new_callsign(callsign)
                                text = """Спасибо, что воспользовались сервисом CFMRDA.ru

Ваш логин - """ + callsign + """
Ваш пароль - """ + password + """

При желании вы можете сменить пароль через форму Восстановление пароля.

73!
С уважением, команда CFMRDA.ru
support@cfmrda.ru"""
                                send_email.send_email(text=text,\
                                    fr=CONF.get('email', 'address'),\
                                    to=email,\
                                    subject="Регистрация на CFMRDA.ru")
                                return web.json_response({'user': user_data})
                return web.Response(text="OK")
            else:
                sql = """
                    select json_build_object(
                    'id', id,
                    'callsign', callsign, 'comment', comment,
                    'blacklist',
                        exists (select from cfm_request_blacklist
                            where cfm_request_blacklist.callsign = correspondent),
                    'stationCallsign', station_callsign, 'rda', rda, 
                    'band', band, 'mode', mode, 
                    'date', to_char(tstamp, 'DD Month YYYY'),
                    'time', to_char(tstamp, 'HH24:MI'),
                    'rcvRST', rec_rst, 'sntRST', sent_rst)
                        from cfm_request_qso
                        where state is null and correspondent = %(callsign)s
                    """
                qso = yield from self._db.execute(sql,\
                    {'callsign': callsign}, True)
                if not admin:
                    yield from self._db.execute("""
                        update cfm_request_qso 
                        set viewed = true, status_tstamp = now()
                        where correspondent = %(callsign)s 
                            and not viewed""",\
                        {'callsign': callsign})
                return web.json_response({'qso': qso})
        else:
            return callsign

    @asyncio.coroutine
    def uploads_hndlr(self, request):
        data = yield from request.json()
        callsign = self.decode_token(data)
        if isinstance(callsign, str):
            if 'delete' in data or 'enable' in data:
                return (yield from self._edit_uploads(data, callsign))
            sql_tmplt = """
                select json_agg(json_build_object('id', id, 
                    'enabled', enabled,
                    'dateStart', to_char(date_start, 'DD mon YYYY'),
                    'dateEnd', to_char(date_end, 'DD mon YYYY'), 
                    'uploadDate', to_char(tstamp, 'DD mon YYYY'), 
                    'uploader', user_cs,
                    'uploadType', upload_type,
                    'extLoggerId', ext_logger_id,
                    'rda', qsos->'rda', 
                    'stations', qsos->'stations', 
                    'qsoCount', qsos->'qsoCount', 
                    'activators', activators)) as data
                from
                    (
                    select * from
                    (select id, enabled, date_start, date_end, tstamp, user_cs,
                        upload_type, ext_logger_id
                    from uploads
                    {}
                    order by tstamp desc
                    {}) as u,
                    lateral 
                    (select json_build_object('rda', array_agg(distinct rda),
                            'stations', array_agg(distinct station_callsign),
                            'qsoCount', count(*)) as qsos
                    from qso
                    where upload_id = u.id) as qsos,
                    lateral 
                    (select array_agg(activator) as activators
                    from activators
                    where upload_id = u.id) as activators
                    ) as data
            """
            admin = self.is_admin(callsign) and 'admin' in data and data['admin']
            params = {}
            where_cond = []
            qso_where_cond = []
            limit_cl = 'limit 100'
            where_cl = ''
            if admin:
                where_cond.append('ext_logger_id is null')
            else:
                where_cond.append('user_cs = %(callsign)s')
                params['callsign'] = callsign
            if 'search' in data and data['search']:
                limit_cl = ''
                if 'rda' in data['search'] and data['search']['rda']:
                    qso_where_cond.append('rda = %(rda)s')
                    params['rda'] = data['search']['rda']
                if 'uploader' in data['search'] and data['search']['uploader']:
                    params['cs_like'] = '%' + \
                        data['search']['uploader'].replace('*', '%') + '%'
                    where_cond.append('user_cs like %(cs_like)s')
                if 'station' in data['search'] and data['search']['station']:
                    params['station_like'] = '%' + \
                        data['search']['station'].replace('*', '%') + '%'
                    qso_where_cond.append('station_callsign like %(station_like)s')
                if 'uploadDate' in data['search'] and data['search']['uploadDate']:
                    where_cond.append('date(tstamp) = %(date)s')
                    params['date'] = data['search']['uploadDate']
            if qso_where_cond:
                where_cond.append("""id in
                    (select upload_id
                    from qso
                    where """ + ' and '.join(qso_where_cond) + ')')
            if where_cond:
                where_cl = 'where ' + ' and '.join(where_cond)
            sql = sql_tmplt.format(where_cl, limit_cl)
            uploads = yield from self._db.execute(sql, params, False)
            return web.json_response(uploads if uploads else [])
        else:
            return callsign

    def send_email_cfm(self, callsign, email):
        token = self.create_token(\
            {'callsign': callsign, 'time': time.time()})
        text = """Пройдите по ссылкe, чтобы подтвердить свою электроную почту на CFMRDA.ru:

""" \
            + CONF.get('web', 'address')\
            + '/aiohttp/confirm_email?token=' + token + """

Если вы не регистрировали учетную запись на CFMRDA.ru, просто игнорируйте это письмо.
Ссылка будет действительна в течение 1 часа.

Служба поддержки CFMRDA.ru"""
        send_email.send_email(text=text,\
            fr=CONF.get('email', 'address'),\
            to=email,\
            subject="CFMRDA.ru - подтверждение электронной почты")

    @asyncio.coroutine
    def register_user(self, data):
        error = None
        if self._json_validator.validate('register', data):
            rc_test = yield from recaptcha.check_recaptcha(data['recaptcha'])
            if rc_test:
                test_callsign = yield from self.get_user_data(data['callsign'])
                if test_callsign:
                    error = 'Этот позывной уже зарегистрирован.'
                else:
                    data['email'] = data['email'].lower()
                    qrz_data = self._qrzcom.get_data(data['callsign'])
                    if qrz_data and 'email' in qrz_data and \
                        qrz_data['email'].lower() == data['email']:
                        yield from self._db.get_object('users',\
                            {'callsign': data['callsign'],\
                            'password': data['password'],\
                            'email': data['email'],\
                            'email_confirmed': False},\
                            True)
                        self.send_email_cfm(data['callsign'], data['email'])
                    else:
                        error =\
                            'Позывной или адрес электронной почты не зарегистрирован на QRZ.com'
            else:
                return CfmRdaServer.response_error_default()
        else:
            return CfmRdaServer.response_error_default()
        if error:
            return web.HTTPBadRequest(text=error)
        else:
            return CfmRdaServer.response_ok()

    @asyncio.coroutine
    def login(self, data):
        error = None
        if self._json_validator.validate('login', data):
            user_data = yield from self.get_user_data(data['callsign'])
            if user_data and user_data['password'] == data['password']:
                if user_data['email_confirmed']:
                    return (yield from self.send_user_data(data['callsign']))
                else:
                    error = 'Необходимо подтвердить адрес электронной почты. ' +\
                            'Вам отправлено повторное письмо с инструкциями.'
                    self.send_email_cfm(data['callsign'], user_data['email'])
            else:
                error = 'Неверный позывной или пароль.'
        else:
            return CfmRdaServer.response_error_default()
        if error:
            return web.HTTPBadRequest(text=error)

    @asyncio.coroutine
    def send_user_data(self, callsign):
        user_data = yield from self.get_user_data(callsign)
        user_data['token'] = self.create_token({'callsign': callsign})
        del user_data['password']
        if callsign in self._site_admins:
            user_data['admin'] = True
        return web.json_response(user_data)

    @asyncio.coroutine
    def cfm_email_hndlr(self, request):
        data = request.query
        callsign = self.decode_token(data, check_time=True)
        if isinstance(callsign, str):
            yield from self._db.param_update('users', {'callsign': callsign},\
                {'email_confirmed': True})
            return web.Response(text='Ваш адрес электронной почты был подтвержден.')
        else:
            return callsign

    @asyncio.coroutine
    def rankings_hndlr(self, request):
        params = {'role': None,\
                'band': None,\
                'mode': None,\
                'from': 1,\
                'to': 100}
        for param in params:
            val = request.match_info.get(param, params[param])
            if val:
                params[param] = val
        cond_tmplt = """role = ''{role}'' and mode = ''{mode}'' and
            band = ''{band}'' and _row >= {from} and _row <= {to}"""
        condition = cond_tmplt.format_map(params)
        rankings = yield from self._db.execute("select rankings_json('" +\
                condition + "') as data", None, False)
        return web.json_response(rankings)

    @asyncio.coroutine
    def qso_hndlr(self, request):
        params = {'callsign': None,\
                'role': None,\
                'rda': None,\
                'band': None,\
                'mode': None}
        for param in params:
            val = request.match_info.get(param, params[param])
            if val:
                params[param] = val
        sql = {'hunter': """
        select json_build_object('band', band,
                'mode', mode,
                'date', to_char(qso.tstamp, 'DD Month YYYY'),
                'time', to_char(qso.tstamp, 'HH24:MI'),
                'stationCallsign', station_callsign,
                'uploadId', uploads.id,
                'uploadType', coalesce( upload_type, 'QSL card'),
                'uploader', uploads.user_cs) as data
        from qso left join uploads on qso.upload_id = uploads.id
        where callsign = %(callsign)s and 
            (enabled or upload_id is null) and
            qso.rda = %(rda)s and
            (qso.band = %(band)s or %(band)s is null) and
            (qso.mode = %(mode)s or %(mode)s is null)
        order by qso.band, qso.mode
        """,\
        'activator': """
            select json_build_object('mode', mode,
                            'band', band,
                            'date', to_char(dt, 'DD Month YYYY'),
                            'uploadId', upload_id,
                            'uploadType', upload_type,
                            'uploader', user_cs, 'count', count) as data
                    from
                        (select mode, band, qso.rda, dt, 
                            count(distinct callsign), 
                            qso.upload_id, user_cs, upload_type
                        from qso, uploads, activators
                        where uploads.id = qso.upload_id and enabled
                            and activators.upload_id = qso.upload_id 
                            and activator = %(callsign)s and
                            qso.rda = %(rda)s and
                            (qso.band = %(band)s or %(band)s is null) and
                            (qso.mode = %(mode)s or %(mode)s is null)
                        group by qso.upload_id, user_cs, upload_type, 
                            mode, band, qso.rda, dt
                        order by band, mode) as l_0
        """}

        @asyncio.coroutine
        def _get_qso(role):
            return (yield from self._db.execute(sql[role], params, True))

        if params['callsign'] and params['role'] and params['rda']:
            data = {'hunter': None}
            if params['role'] == 'hunter':
                for role in sql:
                    data[role] = yield from _get_qso(role)
            else:
                data['activator'] = yield from _get_qso('activator')
            return web.json_response(data)
        else:
            return web.HTTPBadRequest(\
                text='Необходимо ввести позывной, роль и район')

    @asyncio.coroutine
    def hunter_hndlr(self, request):
        callsign = request.match_info.get('callsign', None)
        if callsign:
            data = {}
            new_callsign = yield from self._db.get_new_callsign(callsign)
            if new_callsign:
                callsign = new_callsign
                data['newCallsign'] = new_callsign
            rda = {}
            rda['hunter'] = yield from self._db.execute("""
                select json_object_agg(rda, data) from
                    (select rda, json_agg(json_build_object(
                        'band', band, 'mode', mode)) as data
                    from rda_hunter
                    where hunter = %(callsign)s
                    group by rda) as q
            """, {'callsign': callsign}, False)
            rda['activator'] = yield from self._db.execute("""
                select json_object_agg(rda, data) from
                    (select rda, json_agg(json_build_object(
                        'band', band, 'mode', mode, 'count', callsigns)) as data
                    from rda_activator
                    where activator = %(callsign)s
                    group by rda) as q
            """, {'callsign': callsign}, False)
            if rda['hunter'] or rda['activator']:
                rank = yield from self._db.execute("""
                select rankings_json('callsign = '%(callsign)s'') as data
                """, {'callsign': callsign}, False)
            else:
                rank = False
            data['rda'] = rda
            data['rank'] = rank
            data['oldCallsigns'] = yield from\
                self._db.get_old_callsigns(callsign, True)
            if not data['oldCallsigns']:
                data['oldCallsigns'] = []
            return web.json_response(data)
        else:
            return web.HTTPBadRequest(text='Необходимо ввести позывной')

    @asyncio.coroutine
    def dwnld_qso_hndlr(self, request):
        callsign = request.match_info.get('callsign', None)
        if callsign:
            with (yield from self._db.pool.cursor()) as cur:
                try:
                    yield from cur.execute("""
                        select 
                                rda, 
                                to_char(tstamp, 'DD Mon YYYY') as date, 
                                to_char(tstamp, 'HH24:MI') as time, 
                                band, 
                                mode, 
                                station_callsign, 
                                coalesce(
                                    (
                                        select user_cs 
                                        from uploads 
                                        where uploads.id = qso.upload_id), 
                                    '(QSL card)') as uploader, 
                                to_char(rec_ts, 'DD Mon YYYY') as rec_date
                            from qso 
                            where callsign = %(callsign)s
                    """, {'callsign': callsign})
                    data = yield from cur.fetchall()
                    str_buf = io.StringIO()
                    csv_writer = csv.writer(str_buf, quoting=csv.QUOTE_NONNUMERIC)
                    csv_writer.writerow(['RDA', 'Date', 'Time', 'Band', 'Mode', 'Correspondent',\
                        'Uploader', 'Role', 'DB date'])
                    for row in data:
                        csv_writer.writerow(row)
                    return web.Response(
                        headers={'Content-Disposition': 'Attachment;filename=' +\
                                callsign + datetime.now().strftime('_%d_%b_%Y') +\
                                '.csv'},\
                        body=str_buf.getvalue().encode())
                except Exception:
                    logging.exception('error while importing qso for callsign ' + callsign)
                    return CfmRdaServer.response_error_default()
        else:
            return web.HTTPBadRequest(text='Необходимо ввести позывной')

    @asyncio.coroutine
    def get_qrzru(self, request):
        callsign = request.match_info.get('callsign', None)
        if callsign:
            data = yield from self._qrzru.query(callsign)
            if data:
                return web.json_response(data)
            else:
                return web.json_response(False)
        else:
            return web.HTTPBadRequest(text='Необходимо ввести позывной')

    @asyncio.coroutine
    def _load_qrz_rda(self, callsign):
        check = yield from self._db.execute("""
            select rda 
            from callsigns_rda
            where callsign = %(callsign)s and source = 'QRZ.ru'
                and ts > now() - interval '1 month'""",\
           {'callsign': callsign})
        if not check:
            data = yield from self._qrzru.query(callsign)
            if data and 'state' in data and data['state']:
                yield from self._db.execute("""
                insert into callsigns_rda (callsign, source, rda)
                values (%(callsign)s, 'QRZ.ru', %(rda)s)""",\
                {'callsign': callsign, 'rda': data['state']})


    @asyncio.coroutine
    def view_upload_hndlr(self, request):
        upload_id = request.match_info.get('id', None)
        if upload_id:
            qso = (yield from self._db.execute("""
                select json_agg(json_build_object('callsign', callsign, 
                    'stationCallsign', station_callsign, 'rda', rda, 
                    'band', band, 'mode', mode, 
                    'date', to_char(tstamp, 'DD Month YYYY'),
                    'time', to_char(tstamp, 'HH24:MI')))
                    as data
                from 
                    (select callsign, station_callsign, rda, 
                        band, mode, tstamp
                    from qso 
                    where upload_id = %(upload_id)s
                    order by tstamp) as l_0
            """, {'upload_id': upload_id}, False))
            if qso:
                return web.json_response(qso)
            else:
                return web.json_response(False)
        else:
            return web.HTTPBadRequest(text='Необходимо ввести id файла')

    def decode_token(self, data, check_time=False):
        callsign = None
        if 'token' in data:
            try:
                payload = jwt.decode(data['token'], self._secret,\
                    algorithms=['HS256'])
            except jwt.exceptions.DecodeError:
                return web.HTTPBadRequest(\
                    text='Токен просрочен. Пожалуйста, повторите операцию.')
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
    return CfmRdaServer.response_ok()

if __name__ == '__main__':
    APP = web.Application(client_max_size=100 * 1024 ** 2, loop=asyncio.get_event_loop())
    SRV = CfmRdaServer(APP.loop)
    APP.router.add_get('/aiohttp/test', test_hndlr)
    APP.router.add_post('/aiohttp/test', test_hndlr)
    APP.router.add_post('/aiohttp/login', SRV.login_hndlr)
    APP.router.add_post('/aiohttp/contact_support', SRV.contact_support_hndlr)
    APP.router.add_post('/aiohttp/adif', SRV.adif_hndlr)
    APP.router.add_post('/aiohttp/uploads', SRV.uploads_hndlr)
    APP.router.add_post('/aiohttp/cfm_request_qso', SRV.cfm_request_qso_hndlr)
    APP.router.add_post('/aiohttp/cfm_qsl_qso', SRV.cfm_qsl_qso_hndlr)
    APP.router.add_post('/aiohttp/qsl_admin', SRV.qsl_admin_hndlr)
    APP.router.add_post('/aiohttp/cfm_qso', SRV.cfm_qso_hndlr)
    APP.router.add_post('/aiohttp/cfm_blacklist', SRV.cfm_blacklist_hndlr)
    APP.router.add_post('/aiohttp/chat', SRV.chat_hndlr)
    APP.router.add_post('/aiohttp/old_callsigns',\
        SRV.handler_wrap(SRV.old_callsigns_hndlr, 'oldCallsigns'))
    APP.router.add_post('/aiohttp/old_callsigns_admin',\
        SRV.handler_wrap(SRV.old_callsigns_admin_hndlr, require_admin=True))
    APP.router.add_post('/aiohttp/callsigns_rda',\
        SRV.handler_wrap(SRV.callsigns_rda_hndlr,\
            validation_scheme='callsignsRda', require_callsign=False))
    APP.router.add_post('/aiohttp/ann',\
        SRV.handler_wrap(SRV.ann_hndlr,\
            validation_scheme='ann'))
    APP.router.add_post('/aiohttp/loggers',\
        SRV.handler_wrap(SRV.ext_loggers_hndlr, validation_scheme='extLoggers'))
    APP.router.add_get('/aiohttp/confirm_email', SRV.cfm_email_hndlr)
    APP.router.add_get('/aiohttp/hunter/{callsign}', SRV.hunter_hndlr)
    APP.router.add_get('/aiohttp/qso/{callsign}/{role}/{rda}/{mode:[^{}/]*}/{band:[^{}/]*}', SRV.qso_hndlr)
    APP.router.add_get('/aiohttp/rankings/{role}/{mode}/{band}/{from}/{to}',\
            SRV.rankings_hndlr)
    APP.router.add_get('/aiohttp/correspondent_email/{callsign}',\
            SRV.correspondent_email_hndlr)
    APP.router.add_get('/aiohttp/upload/{id}', SRV.view_upload_hndlr)
    APP.router.add_get('/aiohttp/download/qso/{callsign}', SRV.dwnld_qso_hndlr)
    APP.router.add_get('/aiohttp/qrzru/{callsign}', SRV.get_qrzru)
    web.run_app(APP, path=CONF.get('files', 'server_socket'))
