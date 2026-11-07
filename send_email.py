import smtplib
import os
import ssl
import sys
from send_bark import checkin_succeeded
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime


def send_log_email(log_file='checkin.log'):
    """
    发送签到日志邮件
    
    Args:
        log_file: 日志文件路径
    """
    # 从环境变量读取配置
    smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    sender_email = os.getenv('EMAIL_USERNAME', '')
    sender_password = os.getenv('EMAIL_PASSWORD', '')
    receiver_email = os.getenv('RECEIVER_EMAIL', '').strip() or sender_email
    
    # 检查配置
    if not sender_email or not sender_password:
        print("❌ 邮件配置未设置，跳过发送")
        return True
    
    try:
        smtp_port = int(os.getenv('SMTP_PORT', '587'))
        if not 1 <= smtp_port <= 65535:
            raise ValueError("SMTP_PORT 超出范围")
        # 读取日志内容
        log_content = ""
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                log_content = f.read()
        else:
            log_content = "日志文件不存在"
        
        # 判断签到是否成功（根据日志内容）
        is_success = checkin_succeeded()
        status_emoji = "✅" if is_success else "❌"
        status_text = "成功" if is_success else "失败"
        
        # 创建邮件
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Subject'] = f"{status_emoji} SakuraFrp 签到{status_text} - {datetime.now().strftime('%Y-%m-%d')}"
        
        # 邮件正文
        body = f"""
SakuraFrp 自动签到报告

状态: {status_emoji} {status_text}
时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{'='*50}
日志内容:
{'='*50}

{log_content[-2000:] if len(log_content) > 2000 else log_content}

{'='*50}
此邮件由自动签到系统发送
        """
        
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # 添加日志附件
        if os.path.exists(log_file):
            with open(log_file, 'rb') as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename= {os.path.basename(log_file)}')
            msg.attach(part)
        
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=15,
                                      context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=15)
        
        with server:
            if smtp_port != 465:
                server.starttls(context=ssl.create_default_context())
            server.login(sender_email, sender_password)
            server.send_message(msg)
        
        print(f"✅ 邮件发送成功: {receiver_email}")
        return True

    except Exception:
        print("❌ 邮件发送失败，请检查 SMTP 配置或网络")
        return False


if __name__ == "__main__":
    sys.exit(0 if send_log_email() else 1)

