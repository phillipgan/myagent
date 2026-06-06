"""安全模块 — 审计日志 + PII 脱敏 + 命令白名单 / Security Module — Audit Log + PII Redaction + Command Allowlist"""

import re
import json
import hashlib
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


# PII 检测正则 / PII detection regex patterns
PII_PATTERNS = {
    "email": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
    "phone": r'(\+\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
    "credit_card": r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
    "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
    "ip_address": r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
    "api_key": r'(?:api[_-]?key|token|secret|password)\s*[:=]\s*["\']?[\w\-]{16,}',
}

# 危险命令模式 / Dangerous command patterns
DANGEROUS_COMMANDS = [
    r'\brm\s+-rf\s+/',
    r'\brm\s+-rf\s+~',
    r'\bdd\s+if=',
    r'\bmkfs\b',
    r'\bformat\s+[A-Z]:',  # Windows 磁盘格式化 (e.g. format C:) / Windows disk format
    r'\b:()\s*\{',
    r'\bfork\s+\w*\b',  # fork 炸弹 / fork bomb
    r'>\s*/dev/sd',
    r'\bchmod\s+777\s+/',
    r'\bshutdown\b',
    r'\breboot\b',
    r'\binit\s+[06]',
    r'\bfind\s+/\s+.*-delete\b',  # H-07: find + 删除 / H-07: find + delete
    r'\b(curl|wget)\s+.*\|\s*(ba)?sh\b',  # 管道传输到 shell / pipe to shell
    r'\bpython\s+-c\s+.*import\s+subprocess\b',  # Python 子进程注入 / subprocess via python
    r'\bnc\s+-[el].*-e\s+',  # 反向 shell / reverse shell
    r'\bmsfconsole\b',  # Metasploit / metasploit
    r'/etc/shadow',  # shadow 文件访问 / shadow file access
    r'\biptables\s+-F\b',  # 清空防火墙 / flush firewall
    r'\bkill\s+-9\s+1\b',  # 杀死 init 进程 / kill init
]


class SecurityManager:
    """安全管理器 / Security Manager"""

    def __init__(self, audit_log_dir: str = ""):
        # 默认使用项目内 workspace/logs 目录 / Default to project-local workspace/logs
        if audit_log_dir:
            self.audit_dir = Path(audit_log_dir)
        else:
            _project_root = Path(__file__).resolve().parent.parent
            self.audit_dir = _project_root / "workspace" / "logs"
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self._pii_enabled = True
        self._audit_enabled = True

    def check_command(self, command: str) -> tuple[bool, str]:
        """检查命令是否安全 — 匹配危险命令模式列表。/ Check if command is safe — matches dangerous command patterns.

        Returns:
            (True, "OK") 如果命令安全 / If command is safe
            (False, reason) 如果命令被拦截 / If command is blocked
        """
        for pattern in DANGEROUS_COMMANDS:
            if re.search(pattern, command, re.IGNORECASE):
                return False, f"Dangerous command pattern detected: {pattern}"
        return True, "OK"

    def detect_pii(self, text: str) -> list[dict]:
        """检测文本中的 PII / Detect PII (Personally Identifiable Information) in text"""
        findings = []
        for pii_type, pattern in PII_PATTERNS.items():
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                findings.append({
                    "type": pii_type,
                    "value": match.group(),
                    "position": match.start(),
                })
        return findings

    def redact_pii(self, text: str) -> str:
        """脱敏 PII / Redact PII from text"""
        redacted = text
        for pii_type, pattern in PII_PATTERNS.items():
            if pii_type == "email":
                redacted = re.sub(pattern, lambda m: m.group()[0] + "***@" + m.group().split("@")[-1], redacted)
            elif pii_type == "phone":
                redacted = re.sub(pattern, lambda m: m.group()[:3] + "***" + m.group()[-4:], redacted)
            elif pii_type == "api_key":
                redacted = re.sub(pattern, "[REDACTED]", redacted)
            elif pii_type == "credit_card":
                redacted = re.sub(pattern, "****-****-****-****", redacted)
            elif pii_type == "ip_address":
                # H-08: 保留内网 IP（10.x, 172.16-31.x, 192.168.x, 127.x），脱敏公网 IP / Keep private IPs, redact public IPs
                def _redact_ip(match):
                    ip = match.group()
                    parts = ip.split('.')
                    if len(parts) == 4:
                        first = int(parts[0])
                        # 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8 / Private IP ranges
                        if first == 10 or first == 127 or (first == 172 and 16 <= int(parts[1]) <= 31) or (first == 192 and int(parts[1]) == 168):
                            return ip
                    return f"{parts[0]}.***.***.{parts[3]}" if len(parts) == 4 else ip
                redacted = re.sub(pattern, _redact_ip, redacted)
            else:
                redacted = re.sub(pattern, f"[{pii_type.upper()}_REDACTED]", redacted)
        return redacted

    def audit_log(self, action: str, details):
        """审计日志（H-02: 统一 PII 脱敏）/ Audit log (H-02: unified PII redaction)"""
        if not self._audit_enabled:
            return

        # 统一序列化并脱敏 / Unified serialization and redaction
        if isinstance(details, dict):
            raw = json.dumps(details, ensure_ascii=False)
        else:
            raw = str(details)

        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": self.redact_pii(raw),
        }

        log_file = self.audit_dir / f"audit_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def is_sensitive_request(self, text: str) -> bool:
        """判断请求是否包含敏感数据 / Check if request contains sensitive data"""
        findings = self.detect_pii(text)
        sensitive_types = {"credit_card", "ssn", "api_key"}
        return any(f["type"] in sensitive_types for f in findings)
