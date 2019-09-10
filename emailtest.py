#!/usr/bin/python3
""" Simple test of the mail library """

import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import shared.email

file_dir = os.path.dirname(os.path.abspath(__file__))
with open("%s/developer_cloud_registration_email.txt" % file_dir, "r") as email_file:
    body = email_file.read()

name = "Nobody"
email_address = "nobody@nowhere.org"
uid = "nobody.nowhere"

body = body.format(
    name,
    email_address,
    uid
)

msg = MIMEMultipart('alternative')
msg['Subject'] = "Your Developer Cloud registration"
msg['From'] = "it-support@linaro.org"
msg['To'] = email_address
msg.attach(MIMEText(body, 'plain', 'utf-8'))
shared.email.send_email(msg)
