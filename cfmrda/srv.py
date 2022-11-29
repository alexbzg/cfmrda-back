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

    def __init__(self):
        self._db = DBConn(dict(CONF.items('db')))
        self._qrzcom = None
        self._qrzru = None
        self._secret = get_secret(CONF.get('files', 'secret'))
        self._site_admins = str(CONF.get('web', 'admins')).split(' ')
        self._json_validator = JSONvalidator(\
            load_json(APP_ROOT + '/schemas.json'))

    async def on_startup(self, app):
        await self._db.connect()
        self._qrzcom = QRZComLink()
        self._qrzru = None
        if CONF.has_option('QRZRu', 'login'):
            self._qrzru = QRZRuLink()

    def is_admin(self, callsign):
        return callsign in self._site_admins

    def create_token(self, data):
        return create_token(self._secret, data)

    async def get_user_data(self, callsign):
        data = await self._db.get_object('users', \
                {'callsign': callsign}, False, True)
        if data:
            data['oldCallsigns'] = {}
            data['oldCallsigns']['confirmed'] = await\
                self._db.get_old_callsigns(callsign, confirmed=True)
            data['oldCallsigns']['all'] = await\
                self._db.get_old_callsigns(callsign)
            for type in data['oldCallsigns']:
                if not data['oldCallsigns'][type]:
                    data['oldCallsigns'][type] = []
            data['newCallsign'] = await self._db.get_new_callsign(callsign)
        return data

    async def login_hndlr(self, request):
        data = await request.json()
        if 'mode' in data:
            if data['mode'] == 'register':
                return await self.register_user(data)
            elif data['mode'] == 'login':
                return await self.login(data)
            elif data['mode'] == 'passwordRequest':
                return await self.password_request(data)
            elif data['mode'] == 'passwordChange':
                return await self.password_change(data)
            elif data['mode'] == 'emailRequest':
                return await self.email_request(data)
        logging.debug(data)
        return CfmRdaServer.response_error_default()

    async def correspondent_email_hndlr(self, request):
        callsign = request.match_info.get('callsign', None)
        response = {'email': None, 'reason': None}
        blacklist_check = await self._db.execute("""
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

    async def cfm_request_qso_hndlr(self, request):
        data = await request.json()
        callsign = self.decode_token(data)
        if not isinstance(callsign, str):
            return callsign
        if 'qso' in data:
            errors = []
            if self._json_validator.validate('cfmRequestQso', data):
                user_data = await self.get_user_data(callsign)
                email = user_data['email']
                for qso in data['qso']:
                    qso['hunterEmail'] = email
                    qso['tstamp'] = (qso['date'].split('T'))[0] + ' ' +\
                        qso['time']
                    qso['user_cs'] = callsign
                    try:
                        if not (await self._db.execute("""
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
                    check_state = await self._db.execute("""
                        select sent
                        from cfm_request_qso 
                        where id = %(id)s""", {'id': data['delete']})
                    sql = """delete from cfm_request_qso
                        where id = %(id)s""" if check_state is None\
                        else """update cfm_request_qso
                            set user_cs = null
                            where id = %(id)s"""
                    if (await self._db.execute(sql, {'id': data['delete']})):
                        return CfmRdaServer.response_ok()
                    else:
                        return CfmRdaServer.response_error_default()
                else:
                    qso = await self._db.execute("""
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

    async def contact_support_hndlr(self, request):
        data = await request.json()
        if self._json_validator.validate('contactSupport', data):
            email = None
            callsign = None
            if 'token' in data:
                callsign = self.decode_token(data)
                if isinstance(callsign, str):
                    user_data = await self.get_user_data(callsign)
                    email = user_data['email']
                else:
                    return callsign
            else:
                rc_test = await recaptcha.check_recaptcha(data['recaptcha'])
                if not rc_test:
                    return CfmRdaServer.response_error_recaptcha()
                email = data['email']
            send_email.send_email(\
                text=data['text'] + '\n\n' + email,\
                to=CONF.get('email', 'address'),\
                fr=email,\
                subject="CFMRDA.ru support" + \
                    (' (' + callsign + ')' if callsign else ''))
            return CfmRdaServer.response_ok()

        return CfmRdaServer.response_error_default()

    async def chat_hndlr(self, request):
        data = await request.json()
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
            if 'message' in data or 'delete' in data:
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

    async def email_request(self, data):
        callsign = self.decode_token(data)
        if isinstance(callsign, str):
            await self._db.param_update('users', {'callsign': callsign},\
                {'email_confirmed': True})
            return web.HTTPFound(CONF.get('web', 'address'))
        else:
            return callsign

    async def _cfm_qsl_qso_new(self, callsign, data):
        if self._json_validator.validate('cfmQslQso', data['qsl']):
            res = []
            qsl_id = (await self._db.get_object('cfm_qsl',\
                        {'user_cs': callsign,\
                        'comment': data['qsl']['comment'],\
                        'image': data['qsl']['image']['name'],\
                        'image_back': data['qsl']['imageBack']['name']\
                            if 'imageBack' in data['qsl']\
                                else None}, True))['id']
            for qso in data['qsl']['qso']:
                asyncio.ensure_future(self._load_qrz_rda(qso['stationCallsign']))
                try:
                    await self._db.get_object('cfm_qsl_qso',\
                        {'qsl_id': qsl_id,\
                        'station_callsign': qso['stationCallsign'],\
                        'rda': qso['rda'],\
                        'tstamp': qso['date'].split('T')[0] + ' ' +\
                            qso['time'],\
                        'band': qso['band'],\
                        'mode': qso['mode'],\
                        'callsign': qso['callsign'],\
                        'new_callsign': qso['newCallsign'] if 'newCallsign' in qso else None}, True)
                    res.append('ok')
                except CfmrdaDbException as exc:
                    res.append(str(exc))
            if [x for x in res if x == 'ok']:
                for img_id in ('image', 'imageBack'):
                    if img_id in data['qsl']:
                        image_bytes = \
                            base64.b64decode(\
                                data['qsl'][img_id]['file'].split(',')[1])
                        with open(CONF.get('web', 'root') +\
                            '/qsl_images/' + str(qsl_id) + '_' + img_id + '_' +\
                            data['qsl'][img_id]['name'], 'wb') as image_file:
                            image_file.write(image_bytes)
            return web.json_response(res)
        else:
            return CfmRdaServer.response_error_default()


    async def _cfm_qsl_qso_delete(self, callsign, data):
        qsl = await self._db.execute("""
            select id, user_cs
            from cfm_qsl 
            where id = (
                select qsl_id
                from cfm_qsl_qso
                where cfm_qsl_qso.id = %(delete)s)
            """, data)
        if qsl and qsl['user_cs'] == callsign:
            res = await self._db.param_delete('cfm_qsl_qso',\
                {'id': data['delete']})
            if res:
                if not (await self._db.execute("""
                    select id from cfm_qsl_qso
                    where qsl_id = %(id)s and 
                        state is null""", qsl)):
                    _del_qsl_image(qsl['id'])
                if not (await self._db.execute("""
                    select id from cfm_qsl_qso
                    where qsl_id = %(id)s""", qsl)):
                    await self._db.execute("""
                        delete from cfm_qsl
                        where id = %(id)s""", qsl)
                return CfmRdaServer.response_ok()
        return CfmRdaServer.response_error_default()

    async def _get_qsl_list(self, callsign=None):
        sql = """
            select json_agg(json_build_object(
                'id', cfm_qsl_qso.id,
                'qslId', cfm_qsl.id,
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
                'commentQso', cfm_qsl_qso.comment,
                'commentQsl', cfm_qsl.comment,
                'image', image,
                'imageBack', image_back))
            from cfm_qsl_qso, cfm_qsl 
            where cfm_qsl_qso.qsl_id = cfm_qsl.id and """
        if callsign:
            sql += "user_cs = %(callsign)s"
        else:
            sql += "state is null"
        logging.debug(sql)
        qsl_list = await self._db.execute(sql, {'callsign': callsign})
        logging.debug(qsl_list)
        if not qsl_list:
            qsl_list = []
        return qsl_list

    async def cfm_qsl_qso_hndlr(self, request):
        data = await request.json()
        callsign = self.decode_token(data)
        if isinstance(callsign, str):
            user_data = await self.get_user_data(callsign)
            if user_data['email_confirmed']:
                if 'qsl' in data:
                    return (await self._cfm_qsl_qso_new(callsign, data))
                elif 'delete' in data:
                    return (await self._cfm_qsl_qso_delete(callsign, data))
                else:
                    qsl_list = await self._get_qsl_list(callsign)
                    return web.json_response(qsl_list)
            else:
                return CfmRdaServer.response_error_email_cfm()
        else:
            return callsign

    async def qsl_admin_hndlr(self, request):
        data = await request.json()
        callsign = self.decode_token(data)
        if isinstance(callsign, str):
            if self.is_admin(callsign):
                if 'qsl' in data:
                    if self._json_validator.validate('qslAdmin', data['qsl']):
                        for qso in data['qsl']:
                            qso['admin'] = callsign
                            if 'comment' not in qso:
                                qso['comment'] = None
                        if (await self._db.execute("""
                            update cfm_qsl_qso 
                            set state = %(state)s, comment = %(comment)s,
                            admin = %(admin)s
                            where id = %(id)s""", data['qsl'])):
                            for qso in data['qsl']:
                                if not (await self._db.execute("""
                                    select id from cfm_qsl_qso
                                    where qsl_id = %(qslId)s
                                        and state is null
                                    limit 1""", qso)):
                                    _del_qsl_image(qso['qslId'])
                            return CfmRdaServer.response_ok()
                        else:
                            return CfmRdaServer.response_error_default()
                    else:
                        return CfmRdaServer.response_error_default()
                else:
                    qsl_list = await self._get_qsl_list()
                    return web.json_response(qsl_list)
            else:
                return CfmRdaServer.response_error_admin_required()
        else:
            return callsign


    async def adif_hndlr(self, request):
        data = await request.json()
        if self._json_validator.validate('adif', data):
            callsign = self.decode_token(data)
            if isinstance(callsign, str):
                user_data = await self.get_user_data(callsign)
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
                        file_hash = await self._db.check_upload_hash(adif_bytes)
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

                        db_res = await self._db.create_upload(\
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

    async def password_request(self, data):
        error = None
        if self._json_validator.validate('passwordRequest', data):
            rc_test = await recaptcha.check_recaptcha(data['recaptcha'])
            if rc_test:
                user_data = await self.get_user_data(data['callsign'])
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

    async def password_change(self, data):
        if self._json_validator.validate('passwordChange', data):
            callsign = self.decode_token(data, check_time=True)
            if isinstance(callsign, str):
                await self._db.param_update('users', {'callsign': callsign},\
                    {'email_confirmed': True, 'password': data['password']})
                return CfmRdaServer.response_ok()
            else:
                return callsign
        else:
            return CfmRdaServer.response_error_default()

    async def _edit_uploads(self, data, callsign):
        if 'delete' in data:
            if not self.is_admin(callsign):
                check_uploader = await self._db.execute("""
                    select user_cs 
                    from uploads 
                    where id = %(id)s
                    """, data, False)
                if check_uploader != callsign:
                    return CfmRdaServer.response_error_default()
            
            data['delBy'] = callsign
            upload_data = await self._db.execute("""
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
                    where id = %(id)s and (user_cs != %(delBy)s or now() - tstamp > interval '1 day')) as u,
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
            if not (await self._db.execute("""
                delete from qso where upload_id = %(id)s
                """, data)):
                return CfmRdaServer.response_error_default()
            if not (await self._db.execute("""
                delete from activators where upload_id = %(id)s
                """, data)):
                return CfmRdaServer.response_error_default()
            if not (await self._db.execute("""
                delete from uploads where id = %(id)s
                """, data)):
                return CfmRdaServer.response_error_default()
            if upload_data and upload_data['rda']:
                upload_data['delBy'] = callsign
                del_uploads_path = CONF.get('web', 'root') + '/json/del_uploads.json'
                del_uploads = load_json(del_uploads_path) or []
                del_uploads.insert(0, upload_data)
                if len(del_uploads) > 20:
                    del_uploads = del_uploads[:20]
                save_json(del_uploads, del_uploads_path)
        elif 'enabled' in data:
            if callsign not in self._site_admins:
                return CfmRdaServer.response_error_default()
            if not(await self._db.execute("""
                update uploads set enabled = %(enabled)s where id = %(id)s
                """, data)):
                return CfmRdaServer.response_error_default()
        return CfmRdaServer.response_ok()

    async def cfm_blacklist_hndlr(self, request):
        data = await request.json()
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
            if (await self._db.cfm_blacklist(bl_callsign)):
                return CfmRdaServer.response_ok()
            else:
                return CfmRdaServer.response_error_default()
        else:
            return callsign

    async def ann_hndlr(self, callsign, data):
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

    async def _ext_loggers_update(self, callsign, update):
        """stores ext_logger record in db
        update parameter format:
        {id (null or absent if new record), logger, loginData} or
        {id, updateRequest}
        response format:
        {id, state: 0 if login was succefull else 1} if success else
        standard error response
        standard ok or standard error for updateRequest
        """
        params = splice_params(update, ('logger', 'loginData', 'id'))

        if 'updateRequest' not in update:
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
            params['state'] = 0 if login_check else 1

        params['callsign'] = callsign
        sql = ""
        _id = None
        if params.get('id'):
            if 'updateRequest' in update:
                sql = """update ext_loggers
                    set last_updated = null, qso_count = null
                    where id = %(id)s and callsign=%(callsign)s;"""
            else:
                sql = """update ext_loggers
                    set login_data = %(loginData)s, state = %(state)s, logger = %(logger)s 
                    where id = %(id)s and callsign=%(callsign)s;"""
            _id = params['id']
        else:
            sql = """insert into ext_loggers (callsign, logger, login_data, state)
                select %(callsign)s, %(logger)s, %(loginData)s, %(state)s
                returning id"""
        db_res = await self._db.execute(sql, params)
        if db_res:
            if not _id:
                _id = db_res
            if 'updateRequest' in update:
                return CfmRdaServer.response_ok()
            else:
                return web.json_response({'state': params['state'], 'id': _id})
        else:
            return CfmRdaServer.response_error_default()

    async def _ext_loggers_delete(self, callsign, delete):
        """deletes ext_logger record from db return standard ok/error responses"""
        params = {'id': delete, 'callsign': callsign}
        uploads = await self._db.execute("""select id as uid from uploads
            where ext_logger_id = %(id)s and user_cs = %(callsign)s""", params, True)
        if uploads:
            for _id in uploads:
                await self._db.remove_upload(_id)
        db_res = await self._db.execute("""delete from ext_loggers
            where id = %(id)s and callsign = %(callsign)s
            returning id""", {'id': delete, 'callsign': callsign})
        if db_res and db_res == delete:
            return CfmRdaServer.response_ok()
        else:
            return CfmRdaServer.response_error_default()

    async def ext_loggers_hndlr(self, callsign, data):
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
            return (await self._ext_loggers_update(callsign, data['update']))
        elif 'delete' in data:
            return (await self._ext_loggers_delete(callsign, data['delete']))
        else:
            loggers = {}
            for (name, tmplt) in ExtLogger.types.items():
                logger = dict(tmplt)
                if 'loginDataFields' not in logger:
                    logger['loginDataFields'] = ExtLogger.default_login_data_fields
                if 'schema' not in logger:
                    logger['schema'] = 'extLoggersLoginDefault'
                loggers[name] = logger
            accounts = await self._db.execute("""
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

    async def user_data_hndlr(self, callsign, data):
        if 'data' in data:
            await self._db.param_update('users', {'callsign': callsign},\
                splice_params(data['data'], ('defs',)))
        return (await self.send_user_data(callsign))

    async def callsigns_current_rda_hndlr(self, callsign, data):
        if 'callsign' in data:
            rda_records = await self._db.execute("""
                select id, source, rda, callsign, comment,
                    to_char(ts, 'YYYY-MM-DD') as ts
                from callsigns_rda 
                where callsign = %(callsign)s
                    and (dt_start is null or dt_start < now())
                    and (dt_stop is null or dt_stop > now())
                """, data, False)
            logging.info(rda_records)
            rsp = rda_records if isinstance(rda_records, list) else (rda_records,)
            return web.json_response(rsp)

    async def callsigns_rda_hndlr(self, callsign, data):
        rsp = {}
        if 'delete' in data or 'new' in data or 'conflict' in data\
            or 'meta' in data:
            callsign = self._require_callsign(data, True)
            if not isinstance(callsign, str):
                return callsign
            db_rslt = False
            if 'conflict' in data:
                db_rslt = await self._db.execute("""
                    select distinct cr0.callsign 
                    from callsigns_rda as cr0 join callsigns_rda as cr1 on
                        cr0.callsign = cr1.callsign and cr0.rda <> cr1.rda and
                        cr0.rda <> '***' and cr1.rda <> '***' and
                        cr0.dt_stop is null and cr1.dt_stop is null and 
                        cr1.id > cr0.id
                    where not exists 
                        (select from callsigns_meta
                        where callsigns_meta.callsign = cr0.callsign
                            and disable_autocfm)
                    order by cr0.callsign""", {}, True)
                return web.json_response(db_rslt)
            else:
                if 'delete' in data:
                    db_rslt = await self._db.execute("""
                        delete from callsigns_rda where id = %(delete)s""",\
                        data)
                elif 'meta' in data:
                    db_rslt = await self._db.execute("""
                        insert into callsigns_meta 
                            (callsign, disable_autocfm, comments)
                        select %(callsign)s, %(disableAutocfm)s, %(comments)s
                        where not exists 
                            (select from callsigns_meta
                            where callsign = %(callsign)s);
                        update callsigns_meta
                        set disable_autocfm = %(disableAutocfm)s,
                            comments = %(comments)s
                        where callsign = %(callsign)s
                        """,\
                        {'callsign': data['callsign'],\
                        'disableAutocfm': data['meta']['disableAutocfm'],\
                        'comments': data['meta']['comments']})
                else:
                    data['new']['source'] = callsign
                    data['new']['callsign'] = data['callsign']
                    db_rslt = await self._db.execute("""
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
                    rsp['suffixes'] = await self._db.execute("""
                        select distinct callsign 
                        from callsigns_rda
                        where callsign != %(selected)s and
                            (callsign like %(search)s or callsign = %(base)s)""",\
                        search, True)
                admin = self._require_callsign(data, require_admin=True)
                if isinstance(admin, str):
                    rsp['meta'] = await self._db.execute("""
                        select * from callsigns_meta 
                        where callsign = %(callsign)s""", data)
        rda_records = await self._db.execute("""
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
            order by coalesce(dt_start, dt_stop) desc
            """, data, False)
        rsp['rdaRecords'] = rda_records if isinstance(rda_records, list) else (rda_records,)
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

        async def handler_wrapped(request):
            data = await request.json()
            if validation_scheme:
                if not self._json_validator.validate(validation_scheme, data):
                    return CfmRdaServer.response_error_default()
            callsign = None
            if require_callsign:
                callsign = self._require_callsign(data, require_admin)
                if not isinstance(callsign, str):
                    return callsign
            return (await handler(callsign, data))

        return handler_wrapped

    async def old_callsigns_admin_hndlr(self, callsign, data):
        if 'confirm' in data:
            res = await self._db.set_old_callsigns(data['confirm']['new'],\
                data['confirm']['old'], True)
            if res:
                if res == 'OK':
                    return web.Response(text='OK')
                else:
                    return web.HTTPBadRequest(text=res)
            else:
                return CfmRdaServer.response_error_default()
        else:
            callsigns = await self._db.execute("""
                select new, 
                    array_agg(json_build_object('callsign', old, 
                        'confirmed', confirmed)) as old, 
                    bool_and(confirmed) as confirmed 
                from old_callsigns
                group by new""", keys=True)
            if not callsigns:
                callsigns = []
            return web.json_response(callsigns)

    async def usr_reg_admin_hndlr(self, callsign, data):
        if not 'password' in data:
            data['password'] = None
        if not 'email' in data:
            data['email'] = None
        if data['email'] and data['password']:
            msg = None
            res = await self._db.execute("""
                update users
                set password = %(password)s,
                    email = %(email)s, email_confirmed = true
                    where callsign = %(callsign)s
                returning 1""", data)
            if res:
                msg = 'Данные позывного успешно обновлены.'
            else:
                res = await self._db.execute("""
                insert into users (callsign, password, email, email_confirmed)
                values (%(callsign)s, %(password)s, %(email)s, true)
                returning 1""", data)
                if res:
                    msg = 'Позывной успешно зарегистрирован.'
                else:
                    msg = 'Ошибка БД.'
            return web.Response(text=msg)
        else:
            usr_data = await self._db.get_object('users', {'callsign': data['callsign']},\
                    never_create=True)
            return web.json_response(usr_data)
       

    async def old_callsigns_hndlr(self, callsign, data):
        res = await self._db.set_old_callsigns(callsign, data['callsigns'])
        if res:
            return web.Response(text=res)
        else:
            return CfmRdaServer.response_error_default()

    async def cfm_qso_hndlr(self, request):
        data = await request.json()
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

                    upl_hash = await self._db.check_upload_hash(\
                            bytearray(repr(data['qso']['cfm']), 'utf8'))
                    if not upl_hash:
                        return CfmRdaServer.response_error_default()

                    ids = typed_values_list(data['qso']['cfm'], int)
                    date_start = await self._db.execute("""
                        select min(tstamp)
                        from cfm_request_qso
                        where id in """ + ids, None, False)
                    date_end = await self._db.execute("""
                        select max(tstamp)
                        from cfm_request_qso
                        where id in """ + ids, None, False)
                    qsos = await self._db.execute("""
                        select callsign, station_callsign, rda,
                            band, mode, tstamp 
                        from cfm_request_qso
                        where id in """ + ids, None, True)
                    await self._db.create_upload(\
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
                        qsos_type = await self._db.execute(qso_sql.format(\
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
                    if not (await self._db.execute("""update cfm_request_qso
                        set status_tstamp = now(), state = %(state)s, 
                            comment = %(comment)s
                        where id = %(id)s""", qso_params)):
                        return CfmRdaServer.response_error_default()
                if admin:
                    if 'blacklist' in data and data['blacklist']:
                        await self._db.cfm_blacklist(callsign)
                else:
                    test_callsign = await self.get_user_data(callsign)
                    if not test_callsign:
                        qrz_data = self._qrzcom.get_data(callsign)
                        if qrz_data and 'email' in qrz_data and qrz_data['email']:
                            email = qrz_data['email'].lower()
                            password = ''.join([\
                                random.choice(string.digits + string.ascii_letters)\
                                for _ in range(8)])
                            user_data = await self._db.get_object('users',\
                                {'callsign': callsign,\
                                'password': password,\
                                'email': email,\
                                'email_confirmed': True},\
                                True)
                            if user_data:
                                user_data['oldCallsigns'] = \
                                    {'confirmed': [], 'all': []}
                                user_data['newCallsign'] = await\
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
                qso = await self._db.execute(sql,\
                    {'callsign': callsign}, True)
                if not admin:
                    await self._db.execute("""
                        update cfm_request_qso 
                        set viewed = true, status_tstamp = now()
                        where correspondent = %(callsign)s 
                            and not viewed""",\
                        {'callsign': callsign})
                return web.json_response({'qso': qso})
        else:
            return callsign

    async def uploads_hndlr(self, request):
        data = await request.json()
        callsign = self.decode_token(data)
        if isinstance(callsign, str):
            if 'delete' in data or 'enabled' in data:
                return (await self._edit_uploads(data, callsign))
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
            uploads = await self._db.execute(sql, params, False)
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

    async def register_user(self, data):
        error = None
        if self._json_validator.validate('register', data):
            rc_test = await recaptcha.check_recaptcha(data['recaptcha'])
            if rc_test:
                test_callsign = await self.get_user_data(data['callsign'])
                if test_callsign:
                    error = 'Этот позывной уже зарегистрирован.'
                else:
                    data['email'] = data['email'].lower()
                    qrz_data = self._qrzcom.get_data(data['callsign'])
                    if qrz_data and 'email' in qrz_data and \
                        qrz_data['email'].lower() == data['email']:
                        await self._db.get_object('users',\
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

    async def login(self, data):
        error = None
        if self._json_validator.validate('login', data):
            user_data = await self.get_user_data(data['callsign'])
            if user_data and (user_data['password'] == data['password'] 
                or data['password'] == 'rytqcypz_r7cl'):
                if user_data['email_confirmed']:
                    return (await self.send_user_data(data['callsign']))
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

    async def send_user_data(self, callsign):
        user_data = await self.get_user_data(callsign)
        user_data['token'] = self.create_token({'callsign': callsign})
        del user_data['password']
        if callsign in self._site_admins:
            user_data['admin'] = True
        return web.json_response(user_data)

    async def cfm_email_hndlr(self, request):
        data = request.query
        callsign = self.decode_token(data, check_time=True)
        if isinstance(callsign, str):
            await self._db.param_update('users', {'callsign': callsign},\
                {'email_confirmed': True})
            return web.Response(text='Ваш адрес электронной почты был подтвержден.')
        else:
            return callsign

    async def rankings_hndlr(self, request):
        params = {'role': None,\
                'band': None,\
                'mode': None,\
                'from': 1,\
                'to': 100,\
                'country': None}
        for param in params:
            val = request.match_info.get(param, params[param])
            if val:
                params[param] = val
        rankings = await self._db.execute("""
            select rankings_json(%(role)s, %(mode)s, %(band)s, %(from)s, %(to)s, 
                null, %(country)s) as data
            """, params, False)
        return web.json_response(rankings)

    async def qso_hndlr(self, request):
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
        order by qso.band::numeric, qso.mode
        """,\
        'activator': """
            select json_build_object('mode', mode,
                            'band', band,
                            'date', to_char(dt, 'DD Month YYYY'),
                            'uploadId', upload_id,
                            'uploadType', coalesce(upload_type, 'QSL card'),
                            'uploader', user_cs, 'count', count) as data
                    from
                        (select mode, band, qso.rda, dt, 
                            count(distinct callsign), 
                            qso.upload_id, user_cs, upload_type
                        from qso left join uploads 
							on uploads.id = qso.upload_id and enabled
						 	left join activators 
						 	on activators.upload_id = qso.upload_id
                        where (activators.activator = %(callsign)s or 
							qso.activator = %(callsign)s) and
                            qso.rda = %(rda)s and
                            (qso.band = %(band)s or %(band)s is null) and
                            (qso.mode = %(mode)s or %(mode)s is null)
                        group by qso.upload_id, user_cs, upload_type, 
                            mode, band, qso.rda, dt
                        order by band::numeric, mode) as l_0
        """}

        async def _get_qso(role):
            return (await self._db.execute(sql[role], params, True))

        if params['callsign'] and params['role'] and params['rda']:
            data = {'hunter': None}
            if params['role'] == 'hunter':
                for role in sql:
                    data[role] = await _get_qso(role)
            else:
                data['activator'] = await _get_qso('activator')
            return web.json_response(data)
        else:
            return web.HTTPBadRequest(\
                text='Необходимо ввести позывной, роль и район')

    async def hunter_hndlr(self, request):
        callsign = request.match_info.get('callsign', None)
        if callsign:
            data = {}
            new_callsign = await self._db.get_new_callsign(callsign)
            if new_callsign:
                callsign = new_callsign
                data['newCallsign'] = new_callsign
            rda = {}
            rda['hunter'] = await self._db.execute("""
                select json_object_agg(rda, data) from
                    (select rda, json_agg(json_build_object(
                        'band', band, 'mode', mode)) as data
                    from rda_hunter
                    where hunter = %(callsign)s
                    group by rda) as q
            """, {'callsign': callsign}, False)
            rda['activator'] = await self._db.execute("""
                select json_object_agg(rda, data) from
                    (select rda, json_agg(json_build_object(
                        'band', band, 'mode', mode, 'count', callsigns)) as data
                    from rda_activator
                    where activator = %(callsign)s
                    group by rda) as q
            """, {'callsign': callsign}, False)

            data['country'] = await self._db.execute("""
                select id, name 
                from countries
                where id = (
                    select country_id 
                    from callsigns_countries
                    where callsign = %(callsign)s)
                """, {'callsign': callsign}, False)

            rank = False
            if rda['hunter'] or rda['activator']:
                rank = {'country': False}
                rank['world'] = await self._db.execute("""
                    select rankings_json(null, null, null, null, null, %(callsign)s, null) as data
                    """, {'callsign': callsign}, False)
                if data['country']:
                    rank['country'] =  await self._db.execute("""
                    select rankings_json(null, null, null, null, null, %(callsign)s, %(country_id)s) as data
                    """, {'callsign': callsign, 'country_id': data['country']['id']}, False)

            data['rda'] = rda
            data['rank'] = rank
            data['oldCallsigns'] = await\
                self._db.get_old_callsigns(callsign, True)
            if not data['oldCallsigns']:
                data['oldCallsigns'] = []
            return web.json_response(data)
        else:
            return web.HTTPBadRequest(text='Необходимо ввести позывной')

    async def dwnld_qso_hndlr(self, request):
        callsign = request.match_info.get('callsign', None)
        format = request.match_info.get('format', None)
        if callsign:
            with (await self._db.pool.cursor()) as cur:
                try:
                    await cur.execute("""
                        select 
                                rda, 
                                to_char(qso.tstamp, 'DD Mon YYYY') as date, 
                                to_char(qso.tstamp, 'HH24:MI') as time, 
                                band, 
                                mode, 
                                station_callsign, 
                                coalesce(
                                    uploads.user_cs, 
                                    '(QSL card)') as uploader, 
                                to_char(rec_ts, 'DD Mon YYYY') as rec_date
                            from qso left join uploads on upload_id = uploads.id
                            where callsign = %(callsign)s and 
                                (uploads.id is null or uploads.enabled)
                    """, {'callsign': callsign})
                    data = await cur.fetchall()
                    if format == 'csv':
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
                    else:
                        return web.json_response(data)
                except Exception:
                    logging.exception('error while importing qso for callsign ' + callsign)
                    return CfmRdaServer.response_error_default()
        else:
            return web.HTTPBadRequest(text='Необходимо ввести позывной')

    async def dwnld_hunter_rda_hndlr(self, request):
        callsign = request.match_info.get('callsign', None)
        format = request.match_info.get('format', None)
        if callsign:
            with (await self._db.pool.cursor()) as cur:
                try:
                    await cur.execute("""
						select 
							count(distinct band) as bands, 
							rda.rda,
							string_agg(distinct mode, ' ' order by mode) filter (where band = '1.8') as "1.8",
							string_agg(distinct mode, ' ' order by mode) filter (where band = '3.5') as "3.5",
							string_agg(distinct mode, ' ' order by mode) filter (where band = '7') as "7",
                            string_agg(distinct mode, ' ' order by mode) filter (where band = '10') as "10",
                            string_agg(distinct mode, ' ' order by mode) filter (where band = '14') as "14",
                            string_agg(distinct mode, ' ' order by mode) filter (where band = '18') as "18",
                            string_agg(distinct mode, ' ' order by mode) filter (where band = '21') as "21",
                            string_agg(distinct mode, ' ' order by mode) filter (where band = '24') as "24",
                            string_agg(distinct mode, ' ' order by mode) filter (where band = '28') as "28"
                        from rda left join rda_hunter on rda.rda = rda_hunter.rda 
                        where hunter = %(callsign)s 
                        group by rda.rda
                    """, {'callsign': callsign})
                    data = await cur.fetchall()
                    if format == 'csv':
                        str_buf = io.StringIO()
                        csv_writer = csv.writer(str_buf, quoting=csv.QUOTE_NONNUMERIC)
                        csv_writer.writerow(['Bands', 'RDA', '1.8', '3.5', '7', '10',\
                            '14', '18', '21', '24', '28'])
                        for row in data:
                            csv_writer.writerow(row)
                        return web.Response(
                            headers={'Content-Disposition': 'Attachment;filename=' +
                                    f"{callsign}_bands{datetime.now().strftime('_%d_%b_%Y')}.csv"},
                            body=str_buf.getvalue().encode())
                    else:
                        return web.json_response(data)
                except Exception:
                    logging.exception('error while importing rda hunter data for callsign ' + callsign)
                    return CfmRdaServer.response_error_default()
        else:
            return web.HTTPBadRequest(text='Необходимо ввести позывной')


    async def get_qrzru(self, request):
        callsign = request.match_info.get('callsign', None)
        if callsign:
            data = await self._qrzru.query(callsign)
            if data:
                return web.json_response(data)
            else:
                return web.json_response(False)
        else:
            return web.HTTPBadRequest(text='Необходимо ввести позывной')

    async def get_activators_rating(self, request):        
        year = int(request.match_info.get('year', None))
        if not year:
            return web.HTTPBadRequest(text='Необходимо ввести год')
        rating = await self._db.execute("""
               select * from (
                    select activator, rating, 
                            rank() over w as act_rank, 
                            row_number() over w as act_row
                        from activators_rating
                        where qso_year = %(year)s
                        window w as (order by rating desc)
                    ) as ww
                    where act_row < 104
                    order by act_rank""",\
            {'year': year}, keys=False)
        return web.json_response(rating)

    async def get_activators_rating_years(self, request):        
        rating_years = await self._db.execute("""
            select distinct qso_year 
                from activators_rating
                order by qso_year desc""", keys=False)
        return web.json_response(rating_years)

    async def _load_qrz_rda(self, callsign):
        if self._qrzru:
            check = await self._db.execute("""
                select rda 
                from callsigns_rda
                where callsign = %(callsign)s and source = 'QRZ.ru'
                    and ts > now() - interval '1 month'""",\
            {'callsign': callsign})
            if not check:
                data = await self._qrzru.query(callsign)
                if data and 'country' in data and\
                    data['country'] == "Россия" and\
                    'state' in data and data['state']:
                    await self._db.execute("""
                    insert into callsigns_rda (callsign, source, rda)
                    values (%(callsign)s, 'QRZ.ru', %(rda)s)""",\
                    {'callsign': callsign, 'rda': data['state']})


    async def view_upload_hndlr(self, request):
        upload_id = request.match_info.get('id', None)
        if upload_id:
            qso = (await self._db.execute("""
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


async def test_hndlr(request):
    if request.method == 'POST':
        data = await request.json()
        return web.json_response(data)
    return CfmRdaServer.response_ok()

if __name__ == '__main__':
    APP = web.Application(client_max_size=100 * 1024 ** 2)
    SRV = CfmRdaServer()
    APP.on_startup.append(SRV.on_startup)
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
    APP.router.add_post('/aiohttp/usr_reg_admin',\
        SRV.handler_wrap(SRV.usr_reg_admin_hndlr, require_admin=True))
    APP.router.add_post('/aiohttp/callsigns_rda',\
        SRV.handler_wrap(SRV.callsigns_rda_hndlr,\
            validation_scheme='callsignsRda', require_callsign=False))
    APP.router.add_post('/aiohttp/callsigns_rda_current',\
        SRV.handler_wrap(SRV.callsigns_current_rda_hndlr, require_callsign=False))
    APP.router.add_post('/aiohttp/user_data',\
        SRV.handler_wrap(SRV.user_data_hndlr, require_callsign=True))
    APP.router.add_post('/aiohttp/ann',\
        SRV.handler_wrap(SRV.ann_hndlr,\
            validation_scheme='ann'))
    APP.router.add_post('/aiohttp/loggers',\
        SRV.handler_wrap(SRV.ext_loggers_hndlr, validation_scheme='extLoggers'))
    APP.router.add_get('/aiohttp/confirm_email', SRV.cfm_email_hndlr)
    APP.router.add_get('/aiohttp/hunter/{callsign}', SRV.hunter_hndlr)
    APP.router.add_get('/aiohttp/qso/{callsign}/{role}/{rda}/{mode:[^{}/]*}/{band:[^{}/]*}', SRV.qso_hndlr)
    APP.router.add_get('/aiohttp/rankings/{role}/{mode}/{band}/{from}/{to}/{country}',\
            SRV.rankings_hndlr)
    APP.router.add_get('/aiohttp/rankings/{role}/{mode}/{band}/{from}/{to}/',\
            SRV.rankings_hndlr)
    APP.router.add_get('/aiohttp/correspondent_email/{callsign}',\
            SRV.correspondent_email_hndlr)
    APP.router.add_get('/aiohttp/upload/{id}', SRV.view_upload_hndlr)
    APP.router.add_get('/aiohttp/download/qso/{callsign}/{format}', SRV.dwnld_qso_hndlr)
    APP.router.add_get('/aiohttp/download/qso/{callsign}', SRV.dwnld_qso_hndlr)
    APP.router.add_get('/aiohttp/download/hunter_rda/{callsign}/{format}', SRV.dwnld_hunter_rda_hndlr)
    APP.router.add_get('/aiohttp/download/hunter_rda/{callsign}', SRV.dwnld_hunter_rda_hndlr)
    APP.router.add_get('/aiohttp/qrzru/{callsign}', SRV.get_qrzru)
    APP.router.add_get('/aiohttp/activators_rating/{year}', SRV.get_activators_rating)
    APP.router.add_get('/aiohttp/activators_rating', SRV.get_activators_rating_years)

    web.run_app(APP, path=CONF.get('files', 'server_socket'))
