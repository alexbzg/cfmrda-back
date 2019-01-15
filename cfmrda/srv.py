#!/usr/bin/python3
#coding=utf-8

import asyncio
import logging
import time
import base64
import re
import hashlib
import os
import string
import random
from datetime import datetime

from aiohttp import web
import jwt
import chardet

from common import site_conf, start_logging, APP_ROOT, datetime_format
from db import DBConn, typed_values_list
import send_email
from secret import get_secret, create_token
import recaptcha
from json_utils import load_json, save_json, JSONvalidator
from qrz import QRZComLink
from ham_radio import load_adif, ADIFParseException, strip_callsign
from export import export_msc, export_recent_uploads
from send_cfm_requests import format_qsos

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
        error = None
        if self._json_validator.validate('cfmRequestQso', data):
            email = None
            if 'token' in data:
                callsign = self.decode_token(data)
                if isinstance(callsign, str):
                    user_data = yield from self.get_user_data(callsign)
                    email = user_data['email']
                else:
                    return callsign
            else:
                rc_test = yield from recaptcha.check_recaptcha(data['recaptcha'])
                if rc_test:
                    email = data['email']
                else:
                    return CfmRdaServer.response_error_recaptcha()
            if email:
                for qso in data['qso']:
                    qso['hunterEmail'] = email
                    qso['tstamp'] = (qso['date'].split('T'))[0] + ' ' +\
                        qso['time']
                if not (yield from self._db.execute("""
                    insert into cfm_request_qso 
                    (correspondent, callsign, station_callsign, rda,
                    band, mode, tstamp, hunter_email, 
                    correspondent_email, rec_rst, sent_rst)
                    values (%(correspondent)s, %(callsign)s, 
                    %(stationCallsign)s, %(rda)s, %(band)s, %(mode)s, 
                    %(tstamp)s, %(hunterEmail)s, %(email)s,
                    %(recRST)s, %(sentRST)s)""",\
                    data['qso'], False)):
                    return CfmRdaServer.response_error_default()
        else:
            return CfmRdaServer.response_error_default()
        if error:
            return web.HTTPBadRequest(text=error)
        else:
            return web.Response(text="OK")

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
    def load_adif_file(self, file, callsign, activators=None,\
            station_callsign=None, station_callsign_field=None, rda_field=None):
        error = {'filename': file['name'],\
                'rda': file['rda'] if 'rda' in file else None,\
                'message': 'Ошибка загрузки'}
        try:
            adif_bytes = \
                base64.b64decode(file['file'].split(',')[1])
            adif_hash = hashlib.md5(adif_bytes).hexdigest()
            hash_check = yield from self._db.execute("""
                select id from uploads where hash = %(hash)s
            """, {'hash': adif_hash})
            if hash_check:
                error['message'] = "Файл уже загружен"
                return error
            adif_enc = chardet.detect(adif_bytes)
            adif = adif_bytes.decode(adif_enc['encoding'], 'ignore')
            adif_data = load_adif(adif, \
                station_callsign_field=station_callsign_field,\
                rda_field=rda_field)
            logging.debug('ADIF parsed')

            upl_id = yield from self._db.insert_upload(\
                callsign=callsign,\
                date_start=adif_data['date_start'],\
                date_end=adif_data['date_end'],\
                file_hash=adif_hash,\
                activators=activators |\
                    (set([adif_data['activator']]) if adif_data['activator']\
                    else set([])))
            if not upl_id:
                raise Exception()
            logging.debug('upload_id ' + str(upl_id))

            qso_sql = """insert into qso
                (upload_id, callsign, station_callsign, rda,
                    band, mode, tstamp)
                values (%(upload_id)s, %(callsign)s,
                    %(station_callsign)s, %(rda)s, %(band)s,
                    %(mode)s, %(tstamp)s)"""
            qso_params = []
            for qso in adif_data['qso']:
                qso_params.append({'upload_id': upl_id,\
                    'callsign': qso['callsign'],\
                    'station_callsign': station_callsign or \
                        qso['station_callsign'],\
                    'rda': qso['rda'] if rda_field else file['rda'],\
                    'band': qso['band'],\
                    'mode': qso['mode'],\
                    'tstamp': qso['tstamp']})
            res = yield from self._db.execute(qso_sql, qso_params)
            if res:
                return None
            else:
                raise Exception()
        except Exception as exc:
            if isinstance(exc, ADIFParseException):
                error['message'] = str(exc)
            logging.exception('ADIF load error')
            return error

    @asyncio.coroutine
    def _cfm_qsl_qso_new(self, callsign, data):
        if self._json_validator.validate('cfmQslQso', data['qso']):
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
                'callsign', callsign,
                'stationCallsign', station_callsign,
                'rda', rda,
                'band', band,
                'mode', mode,
                'newCallsign', new_callsign,
                'date', to_char(tstamp, 'DD mon YYYY'),
                'time', to_char(tstamp, 'HH24:MI'),
                'state', state,
                'comment', comment,
                'image', image))
            from cfm_qsl_qso 
            where """
        if callsign:
            sql += "user_cs = %(callsign)s"
        else:
            sql += "state is null"
        qsl_list = yield from self._db.execute(sql, {'callsign': callsign})
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
                        if (yield from self._db.execute("""
                            update cfm_qsl_qso 
                            set state = %(state)s, comment = %(comment)s
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
                    response = {'filesLoaded': 0, 'errors': []}
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
                        error = yield from self.load_adif_file(file, callsign,\
                                activators=activators,\
                                station_callsign=station_callsign,\
                                station_callsign_field=station_callsign_field,\
                                rda_field=rda_field)
                        if error:
                            response['errors'].append(error)
                        else:
                            response['filesLoaded'] += 1
                    if response['filesLoaded'] and 'skipRankings' not in data:
                        logging.debug('running export_rankings')
                        yield from export_msc(CONF)
                        yield from export_recent_uploads(CONF)
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
        elif 'enabled' in data:
            if callsign not in self._site_admins:
                return CfmRdaServer.response_error_default()
            if not(yield from self._db.execute("""
                update uploads set enabled = %(enabled)s where id = %(id)s
                """, data)):
                return CfmRdaServer.response_error_default()
        yield from export_msc(CONF)
        yield from export_recent_uploads(CONF)
        return CfmRdaServer.response_ok()

    @asyncio.coroutine
    def cfm_blacklist_hndlr(self, request):
        data = yield from request.json()
        callsign = self.decode_token(data)
        if isinstance(callsign, str):
            if (yield from self._db.execute("""
                insert into cfm_request_blacklist
                values (%(callsign)s)""",\
                {'callsign': callsign}, False)):
                return CfmRdaServer.response_ok()
            else:
                return CfmRdaServer.response_error_default()
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
            if require_callsign:
                callsign = self.decode_token(data)
                if isinstance(callsign, str):
                    if require_admin:
                        if not self.is_admin(callsign):
                            return CfmRdaServer.response_error_admin_required()
                    return (yield from handler(callsign, data))
                else:
                    return callsign

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
        callsign = self.decode_token(data)
        if isinstance(callsign, str):
            if 'qso' in data:
                if 'cfm' in data['qso'] and data['qso']['cfm']:
                    logging.debug(data)
                    upl_hash = hashlib.md5(bytearray(repr(data['qso']['cfm']),\
                        'utf8')).hexdigest()
                    ids = typed_values_list(data['qso']['cfm'], int)
                    date_start = yield from self._db.execute("""
                        select min(tstamp)
                        from cfm_request_qso
                        where id in """ + ids, None, False)
                    date_end = yield from self._db.execute("""
                        select max(tstamp)
                        from cfm_request_qso
                        where id in """ + ids, None, False)
                    file_id = yield from self._db.insert_upload(\
                        callsign=callsign,\
                        date_start=date_start,\
                        date_end=date_end,\
                        file_hash=upl_hash,\
                        upload_type='email CFM',\
                        activators=[callsign])
                    if not file_id or not (yield from self._db.execute("""
                        insert into qso (upload_id, callsign, station_callsign,
                            rda, band, mode, tstamp)
                        select %(file_id)s, callsign, station_callsign, rda,
                            band, mode, tstamp 
                        from cfm_request_qso
                        where id in """ + ids,\
                        {'file_id': file_id})):
                        return CfmRdaServer.response_error_default()
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
                for email in qsos:
                    text = """Здравствуйте.

По вашему email-запросу на сайте CFMRDA.ru """
                    if 'cfm' in qsos[email]:
                        text += "были подтверждены следующие QSO:\n" +\
                            format_qsos(qsos[email]['cfm'])
                    if 'reject' in qsos[email]:
                        text += "В подтверждении следующих QSO корреспондент отказал:\n" +\
                            format_qsos(qsos[email]['reject'])
                    text += """

Спасибо. 73!
Команда CFMRDA.ru"""
                    send_email.send_email(text=text,\
                        fr=CONF.get('email', 'address'),\
                        to=email,\
                        subject="Подтверждение QSO на CFMRDA.ru")
                all_ids = []
                for _type in data['qso']:
                    all_ids += data['qso'][_type]
                if all_ids:
                    yield from self._db.execute("""delete from cfm_request_qso
                        where id in """ + typed_values_list(all_ids, int))
                yield from export_msc(CONF)
                yield from export_recent_uploads(CONF)
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
                qso = yield from self._db.execute("""
                    select json_build_object(
                    'id', id,
                    'callsign', callsign, 
                    'stationCallsign', station_callsign, 'rda', rda, 
                    'band', band, 'mode', mode, 
                    'date', to_char(tstamp, 'DD Month YYYY'),
                    'time', to_char(tstamp, 'HH24:MI'),
                    'rcvRST', rec_rst, 'sntRST', sent_rst)
                        from cfm_request_qso
                        where correspondent = %(callsign)s
                    """, {'callsign': callsign}, True)
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
                    'rda', qsos->'rda', 
                    'stations', qsos->'stations', 
                    'qsoCount', qsos->'qsoCount', 
                    'activators', activators)) as data
                from
                    (select id, enabled, date_start, date_end, tstamp, user_cs,
                        upload_type,
                        (select json_build_object('rda', array_agg(distinct rda), 
                            'stations', array_agg(distinct station_callsign), 
                            'qsoCount', count(*)) 
                        from qso 
                        where upload_id = uploads.id) as qsos,
                        (select array_agg(activator) 
                        from activators 
                        where upload_id = uploads.id) as activators
                    from uploads 
                    {}
                    order by tstamp desc) as data
            """
            admin = self.is_admin(callsign) and 'admin' in data and data['admin']
            sql = sql_tmplt.format('' if admin else 'where user_cs = %(callsign)s')
            uploads = yield from self._db.execute(sql, {'callsign': callsign},\
                False)
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
    def hunter_hndlr(self, request):
        callsign = request.match_info.get('callsign', None)
        if callsign:
            new_callsign = yield from self._db.get_new_callsign(callsign)
            if new_callsign:
                return web.json_response({'newCallsign': new_callsign})
            qso = yield from self._db.execute("""
                select json_object_agg(rda, data) as data
                from
                    (select rda, json_object_agg(type, data) as data
                    from
                        (select qso.rda, 'hunter' as type,
                            json_agg(json_build_object('band', band,
                                'mode', mode,
                                'date', to_char(qso.tstamp, 'DD Month YYYY'),
                                'time', to_char(qso.tstamp, 'HH24:MI'),
                                'stationCallsign', station_callsign,
                                'uploadId', uploads.id,
                                'uploadType', coalesce( upload_type, 'QSL card'),
                                'uploader', uploads.user_cs)) as data
                        from qso left join uploads on qso.upload_id = uploads.id
                        where callsign = %(callsign)s and 
                            (enabled or upload_id is null)
                        group by qso.rda
                        union all
                        select rda, 'activator' as type,
                            json_agg(json_build_object('mode', mode,
                                'band', band,
                                'date', to_char(dt, 'DD Month YYYY'),
                                'uploadId', upload_id,
                                'uploadType', upload_type,
                                'uploader', user_cs, 'count', count)) as data
                        from
                            (select mode, band, qso.rda, dt, 
                                count(distinct callsign), 
                                qso.upload_id, user_cs, upload_type
                            from qso, uploads, activators
                            where uploads.id = qso.upload_id and enabled
                                and activators.upload_id = qso.upload_id 
                                and activator = %(callsign)s
                            group by qso.upload_id, user_cs, upload_type, 
                                mode, band, qso.rda, dt) as l_0
                        group by rda) as l_1
                    group by rda) as l_2
            """, {'callsign': callsign}, False)
            if qso:
                rank = yield from self._db.execute("""
                select rankings_json('callsign = '%(callsign)s'') as data
                """, {'callsign': callsign}, False)
                data = {'qso': qso, 'rank': rank}
                data['oldCallsigns'] = yield from\
                    self._db.get_old_callsigns(callsign, True)
                return web.json_response(data)
            else:
                return web.json_response(False)
        else:
            return web.HTTPBadRequest(text='Необходимо ввести позывной')

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
    APP = web.Application(client_max_size=100 * 1024 ** 2)
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
    APP.router.add_get('/aiohttp/confirm_email', SRV.cfm_email_hndlr)
    APP.router.add_get('/aiohttp/hunter/{callsign}', SRV.hunter_hndlr)
    APP.router.add_get('/aiohttp/correspondent_email/{callsign}',\
            SRV.correspondent_email_hndlr)
    APP.router.add_get('/aiohttp/upload/{id}', SRV.view_upload_hndlr)
    web.run_app(APP, path=CONF.get('files', 'server_socket'))
