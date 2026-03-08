import smtplib
from email.message import EmailMessage

HOST = "smtp.qq.com"
PORT = 465  # 和 .env 里一致
USER = "2745469836@qq.com"
PWD = "vywpwaswlbxddcdf"
TO = "2745469836@qq.com"  # 可以发给自己

def main():
    msg = EmailMessage()
    msg["Subject"] = "SMTP 测试邮件"
    msg["From"] = USER
    msg["To"] = TO
    msg.set_content("这是一封来自 Python 的测试邮件。")

    with smtplib.SMTP_SSL(HOST, PORT) as server:
        server.set_debuglevel(1)  # 打印完整收发日志，方便排查
        server.login(USER, PWD)
        server.send_message(msg)

if __name__ == "__main__":
    main()