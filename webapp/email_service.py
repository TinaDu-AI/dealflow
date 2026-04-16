"""Simple email service with console fallback for dev mode."""
from __future__ import annotations

import os
import random
import smtplib
import ssl
import string
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# Load .env file from webapp/ directory if env vars not already set
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.163.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")

# If no SMTP credentials configured, fall back to console print
CONSOLE_MODE = not SMTP_USER


def generate_code(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


def send_verification_code(to_email: str, code: str) -> None:
    """Send a verification code. Falls back to server console if SMTP not configured."""
    if CONSOLE_MODE:
        print(f"\n{'=' * 60}")
        print(f"  [MFV 验证码]  收件人: {to_email}")
        print(f"  验证码: {code}  (有效期 10 分钟)")
        print(f"{'=' * 60}\n", flush=True)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"MFV Deal Flow 验证码：{code}"
    msg["From"] = SMTP_USER
    msg["To"] = to_email

    text_body = f"您的 MFV Deal Flow 验证码是：{code}\n有效期 10 分钟。"
    html_body = f"""
    <div style="font-family: -apple-system, 'PingFang SC', sans-serif;
                max-width: 420px; margin: 40px auto; padding: 32px 24px;
                background: #f9fafb; border-radius: 16px;">
      <h2 style="color: #7c3aed; margin: 0 0 16px;">MFV Deal Flow</h2>
      <p style="color: #374151; margin: 0 0 8px;">您的注册验证码是：</p>
      <div style="font-size: 40px; font-weight: 800; letter-spacing: 10px;
                  color: #111827; margin: 16px 0; font-variant-numeric: tabular-nums;">
        {code}
      </div>
      <p style="color: #6b7280; font-size: 13px; margin: 0;">
        有效期 10 分钟。如果不是您本人操作，请忽略此邮件。
      </p>
    </div>
    """

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    context = ssl.create_default_context()
    last_err: Exception | None = None
    for attempt in range(3):          # retry up to 3× on transient SMTP errors
        try:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=10) as server:
                server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(SMTP_USER, to_email, msg.as_string())
            return                    # success
        except Exception as e:
            last_err = e
            print(f"[email] attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                time.sleep(1.5)
    raise last_err                    # all 3 attempts failed
