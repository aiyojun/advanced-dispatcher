import logging
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def email(username, password, smtp_server, receivers,
          title, text, text_type='plain', copy_to=None, attach_file=None, email_address=None):
    if username is None or smtp_server is None:
        logging.warning("Email username: {}, smtp server: {}".format(username, smtp_server))
        return
    __charset__ = 'utf-8'
    msg_ctx = MIMEMultipart()
    msg_ctx['Subject'] = Header(title, __charset__)
    msg_ctx['From'] = Header("<{}>".format(username), __charset__)
    msg_ctx['To'] = Header(", ".join(["<{}>".format(r) for r in receivers]))
    if copy_to is not None:
        msg_ctx['Cc'] = Header(", ".join(["<{}>".format(r) for r in copy_to]))
        receivers += copy_to
    msg_ctx.attach(MIMEText(text, text_type, __charset__))
    if attach_file is not None:
        fp = MIMEText(open(attach_file, 'rb').read(), 'base64', __charset__)
        fp['Content-Type'] = 'application/octet-stream'
        fp.add_header('Content-Disposition', 'attachment',
                      filename=Header(attach_file.split('/').pop(), __charset__).encode())
        msg_ctx.attach(fp)
    try:
        host = smtp_server.split(':')
        smtp_obj = smtplib.SMTP()
        smtp_obj.connect(host[0], int(host[1]))
        smtp_obj.login(username, password)
        smtp_obj.sendmail(username if email_address is None else email_address, receivers, msg_ctx.as_string())
        smtp_obj.quit()
    except smtplib.SMTPException as e:
        logging.error(">> send email failed, {}. Current email address: {}"
                      .format(str(e), username if email_address is None else email_address))
