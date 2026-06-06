"""邮件工具 / Email Tool — IMAP Read + SMTP Send

支持双账户配置（通过环境变量）：
Supports dual-account config (via env vars):
  - Gmail: imap.gmail.com:993 / smtp.gmail.com:587 (STARTTLS)
  - 163邮箱: imap.163.com:993 / smtp.163.com:465 (SSL)

安全设计:
Safety Design:
  - C-06: 移除硬编码邮箱 / Remove hardcoded emails, return error if unconfigured
  - H-09: IMAP 同步操作用 asyncio.to_thread() / Wrap sync IMAP in asyncio.to_thread()
  - IMAP 搜索字符串注入防护 / IMAP search string injection protection
  - SMTP/IMAP 在 finally 中关闭 / SMTP/IMAP connections closed in finally block
"""

import os
import re
import email
import asyncio
import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional
from .base import BaseTool, ToolResult


def _sanitize_imap_search(query: str) -> str:
    """清理 IMAP 搜索字符串 / Sanitize IMAP search string — remove control/special chars"""
    cleaned = re.sub(r'[\x00-\x1f\x7f\\"]', '', query)
    return cleaned[:200]


class EmailReadTool(BaseTool):
    name = "email_read"
    description = "Read emails from IMAP inbox"

    async def execute(
        self,
        action: str = "list",
        folder: str = "INBOX",
        limit: int = 10,
        uid: int | None = None,
        search: str | None = None,
        account: str = "gmail",
    ) -> ToolResult:
        """读取邮件 / Read email"""
        import imaplib

        accounts = self._get_accounts()
        if account not in accounts:
            return ToolResult(error=f"Unknown account: {account}. Available: {list(accounts.keys())}", success=False)

        acc = accounts[account]

        # C-06: 检查账户是否完整配置 / Check if account is fully configured
        if not acc.get("email") or not acc.get("password"):
            return ToolResult(
                error=f"Account '{account}' not configured. Set environment variables for email and password.",
                success=False,
            )

        # H-09: 将同步 IMAP 操作包装在 asyncio.to_thread / Wrap sync IMAP in asyncio.to_thread
        try:
            result = await asyncio.to_thread(
                self._imap_operation, acc, action, folder, limit, uid, search
            )
            return result
        except Exception as e:
            return ToolResult(error=str(e), success=False)

    def _imap_operation(self, acc, action, folder, limit, uid, search) -> ToolResult:
        """同步 IMAP 操作 / Sync IMAP operations (in thread pool)"""
        import imaplib

        imap = None
        try:
            imap = imaplib.IMAP4_SSL(acc["imap_server"], acc["imap_port"])
            imap.login(acc["email"], acc["password"])
            imap.select(folder)

            if action == "list" or action == "search":
                if search:
                    safe_search = _sanitize_imap_search(search)
                    status, data = imap.search(None, "SUBJECT", safe_search)
                else:
                    status, data = imap.search(None, "ALL")

                if status != "OK":
                    return ToolResult(error="Search failed", success=False)

                uids = data[0].split()
                recent_uids = uids[-limit:] if uids else []

                if not recent_uids:
                    return ToolResult(output="No emails found.")

                results = []
                for uid_val in recent_uids:
                    status, msg_data = imap.fetch(uid_val, "(RFC822)")
                    if status != "OK":
                        continue
                    msg = email.message_from_bytes(msg_data[0][1])
                    subject = email.header.decode_header(msg["Subject"])[0]
                    subject_text = subject[0].decode(subject[1] or "utf-8") if isinstance(subject[0], bytes) else str(subject[0])
                    from_addr = msg["From"]
                    date = msg["Date"]
                    results.append(f"UID: {uid_val.decode()} | From: {from_addr} | Date: {date}\nSubject: {subject_text}")

                return ToolResult(output="\n---\n".join(results))

            elif action == "read" and uid:
                status, msg_data = imap.fetch(str(uid), "(RFC822)")
                if status != "OK":
                    return ToolResult(error=f"Email {uid} not found", success=False)

                msg = email.message_from_bytes(msg_data[0][1])
                subject = email.header.decode_header(msg["Subject"])[0]
                subject_text = subject[0].decode(subject[1] or "utf-8") if isinstance(subject[0], bytes) else str(subject[0])

                body = self._get_body(msg)

                return ToolResult(
                    output=f"From: {msg['From']}\nTo: {msg['To']}\nDate: {msg['Date']}\nSubject: {subject_text}\n\n{body[:3000]}"
                )

            return ToolResult(output="Done")

        finally:
            if imap:
                try:
                    imap.close()
                    imap.logout()
                except Exception:
                    pass

    def _get_body(self, msg) -> str:
        """提取邮件正文 / Extract email body"""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    try:
                        return part.get_payload(decode=True).decode("utf-8", errors="replace")
                    except Exception:
                        pass
        else:
            try:
                return msg.get_payload(decode=True).decode("utf-8", errors="replace")
            except Exception:
                pass
        return ""

    def _get_accounts(self) -> dict:
        """C-06: 获取邮件账户配置 — 无硬编码默认值 / Get email account config — no hardcoded defaults"""
        gmail_email = os.environ.get("GMAIL_ADDRESS", "")
        gmail_password = os.environ.get("GMAIL_APP_PASSWORD", "")
        mail163_email = os.environ.get("MAIL_163_ADDRESS", "")
        mail163_password = os.environ.get("163_IMAP_PASSWORD", "")

        accounts = {}
        if gmail_email and gmail_password:
            accounts["gmail"] = {
                "imap_server": "imap.gmail.com",
                "imap_port": 993,
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "email": gmail_email,
                "password": gmail_password,
            }
        if mail163_email and mail163_password:
            accounts["163"] = {
                "imap_server": "imap.163.com",
                "imap_port": 993,
                "smtp_server": "smtp.163.com",
                "smtp_port": 465,
                "email": mail163_email,
                "password": mail163_password,
            }
        return accounts

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "email_read",
                "description": "Read emails from IMAP inbox. Actions: 'list' recent emails, 'read' a specific email by UID, 'search' by subject.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["list", "read", "search"], "description": "Action to perform"},
                        "folder": {"type": "string", "description": "IMAP folder (default: INBOX)"},
                        "limit": {"type": "integer", "description": "Number of emails (default: 10)"},
                        "uid": {"type": "integer", "description": "Email UID for 'read' action"},
                        "search": {"type": "string", "description": "Search query for 'search' action"},
                        "account": {"type": "string", "enum": ["gmail", "163"], "description": "Email account"},
                    },
                    "required": ["action"]
                }
            }
        }


class EmailSendTool(BaseTool):
    name = "email_send"
    description = "Send an email via SMTP"

    async def execute(
        self,
        to: str,
        subject: str,
        body: str,
        html: bool = False,
        account: str = "gmail",
        attachment_path: str | None = None,
    ) -> ToolResult:
        """发送邮件 / Send email"""
        # C-06: 无硬编码邮箱 / No hardcoded email
        gmail_email = os.environ.get("GMAIL_ADDRESS", "")
        gmail_password = os.environ.get("GMAIL_APP_PASSWORD", "")
        mail163_email = os.environ.get("MAIL_163_ADDRESS", "")
        mail163_password = os.environ.get("163_IMAP_PASSWORD", "")

        accounts = {}
        if gmail_email and gmail_password:
            accounts["gmail"] = {
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "email": gmail_email,
                "password": gmail_password,
            }
        if mail163_email and mail163_password:
            accounts["163"] = {
                "smtp_server": "smtp.163.com",
                "smtp_port": 465,
                "email": mail163_email,
                "password": mail163_password,
            }

        if account not in accounts:
            available = list(accounts.keys()) or ["(none configured — set GMAIL_ADDRESS and GMAIL_APP_PASSWORD env vars)"]
            return ToolResult(error=f"Account '{account}' not configured. Available: {available}", success=False)

        acc = accounts[account]

        try:
            msg = MIMEMultipart()
            msg["From"] = acc["email"]
            msg["To"] = to
            msg["Subject"] = subject

            msg.attach(MIMEText(body, "html" if html else "plain", "utf-8"))

            # 附件 / Attachments
            if attachment_path:
                from pathlib import Path
                fpath = Path(attachment_path).expanduser()
                if fpath.exists():
                    with open(fpath, "rb") as f:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(f.read())
                        encoders.encode_base64(part)
                        part.add_header("Content-Disposition", "attachment", filename=fpath.name)
                        msg.attach(part)

            smtp = None
            try:
                if acc["smtp_port"] == 587:
                    smtp = aiosmtplib.SMTP(hostname=acc["smtp_server"], port=acc["smtp_port"], use_tls=False)
                    await smtp.connect()
                    await smtp.starttls()
                else:
                    smtp = aiosmtplib.SMTP(hostname=acc["smtp_server"], port=acc["smtp_port"], use_tls=True)
                    await smtp.connect()

                await smtp.login(acc["email"], acc["password"])
                await smtp.send_message(msg)
                return ToolResult(output=f"Email sent to {to}: {subject}")
            finally:
                if smtp:
                    try:
                        await smtp.quit()
                    except Exception:
                        pass

        except Exception as e:
            return ToolResult(error=str(e), success=False)

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "email_send",
                "description": "Send an email via SMTP. Supports HTML body and file attachments.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Recipient email address"},
                        "subject": {"type": "string", "description": "Email subject"},
                        "body": {"type": "string", "description": "Email body content"},
                        "html": {"type": "boolean", "description": "Is body HTML? (default: false)"},
                        "account": {"type": "string", "enum": ["gmail", "163"], "description": "Account to send from"},
                        "attachment_path": {"type": "string", "description": "Optional file attachment path"},
                    },
                    "required": ["to", "subject", "body"]
                }
            }
        }
