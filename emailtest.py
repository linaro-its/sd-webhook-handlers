#!/usr/bin/python3
""" Simple test of the mail library """

import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import shared.globals
import shared.email

shared.globals.initialise_config()

body = "This is a very simple email test.\r\n"

msg = MIMEMultipart('alternative')
msg['Subject'] = "Your Developer Cloud registration"
msg['From'] = "it-support@linaro.org"
msg['To'] = "nobody@nowhere.org"
msg.attach(MIMEText(body, 'plain', 'utf-8'))
shared.email.send_email(msg)
