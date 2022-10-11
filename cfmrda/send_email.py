#!/usr/bin/python3
#coding=utf-8

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

from common import site_conf

def send_email(**email):
    conf = site_conf()
    my_address = conf.get('email', 'address')
    msg = MIMEMultipart()
    msg.attach(MIMEText(email['text'].encode('utf-8'), 'plain', 'UTF-8'))
    msg['reply-to'] = email['fr']
    msg['to'] = email['to']
    msg['MIME-Version'] = "1.0"
    msg['Subject'] = email['subject']
    msg['Content-Type'] = "text/plain; charset=utf-8"
    msg['Content-Transfer-Encoding'] = "quoted-printable"

    if 'attachments' in email and email['attachments']:
        for item in email['attachments']:
            part = MIMEApplication(item['data'], Name=item['name'])
            part['Content-Disposition'] = 'attachment; filename="%s"' % item['name']
            msg.attach(part)
    try:
        server = smtplib.SMTP_SSL(conf.get('email', 'smtp'))
        server.login(conf.get('email', 'login'), conf.get('email', 'password'))
        server.sendmail(my_address, msg['to'], str(msg))
        return True
    except Exception as exc:
        logging.exception('error sending email')
        return False

