from datetime import datetime

from aiohttp import web

def response_error_default():
    return web.HTTPBadRequest(\
        text='Ошибка сайта. Пожалуйста, попробуйте позднее.')

def response_error_recaptcha():
    return web.HTTPBadRequest(text='Проверка на робота не пройдена ' +\
        'или данные устарели. Попробуйте еще раз.')

def response_ok():
    return web.Response(text='OK')

def response_error_email_cfm():
    return web.HTTPUnauthorized(text='Ваш адрес электронной почты не подтвержден.')

def response_error_admin_required():
    return web.HTTPUnauthorized(text='Необходимы права администратора сайта.')

def response_error_unauthorized():
    return web.HTTPUnauthorized(text='Нет прав для выполнения этого действия.')

def response_csv(callsign, str_buf):
    return web.Response(
        headers={
            'Content-Disposition':
                (f'Attachment;filename={callsign}' +
                    f'{datetime.now().strftime("_%d_%b_%Y")}.csv')},
        body=str_buf.getvalue().encode()
    )
