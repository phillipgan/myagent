"""Shell 执行工具 / Shell Execution Tool — Mirrors OpenClaw Skills Compatible exec tool

安全层级：
Security Layers:
  1. 白名单检查 / Allowlist check — only predefined safe command prefixes
  2. 黑名单检查 / Blacklist check — block known dangerous patterns (rm -rf /, dd, mkfs)
  3. 注入防护 / Injection protection — block ; $() ` newline metachars
  4. 管道目标检查 / Pipe target check — block piping to shell/interpreter
  5. SecurityManager 二次检查 / Secondary SecurityManager pattern check

输出处理：自动剥离 ANSI 转义码。
Output: auto-strip ANSI escape codes to avoid color codes in chat.

修复:
Fixes:
- V7-C01: Shell 元字符过滤 / Shell metachar filtering prevents injection
- V8-C02: 保留 shell=True / Keep shell=True for pipe/redirect, only block dangerous metachars
- C-08: 延迟初始化 SecurityManager / Lazy init, avoid import side effects
"""

import asyncio
import re
import shlex
import logging
from pathlib import Path
from .base import BaseTool, ToolResult

# C-08: 延迟初始化 / Lazy init, avoid creating dirs on import
_security = None
logger = logging.getLogger(__name__)

# 允许的命令前缀白名单（Linux + Windows 跨平台）/ Allowed command prefix allowlist (cross-platform)
_ALLOWED_COMMAND_PREFIXES = (
    # Linux/macOS 命令 / Linux/macOS commands
    "ls", "cat", "head", "tail", "wc", "find", "grep", "du", "df",
    "echo", "pwd", "whoami", "date", "uname", "env", "which",
    "curl", "wget",
    "python3", "python", "pip", "pip3",
    "git", "gh",
    "npm", "node", "npx",
    "docker", "docker-compose",
    "jq",
    "sort", "uniq", "awk", "sed", "tr", "cut", "xargs",
    "tar", "zip", "unzip", "gzip",
    "mkdir", "cp", "mv", "touch", "rm",
    "ping", "nslookup", "dig", "host",
    "ps", "top", "free", "uptime",
    "tree", "file", "stat",
    "diff", "patch",
    # Windows 命令 / Windows commands
    "dir", "type", "more", "findstr", "where", "certutil",
    "systeminfo", "tasklist", "taskkill", "netstat",
    "set", "cls", "chcp", "copy", "move", "del",
    "powershell", "pwsh",
)

# 禁止的命令模式（黑名单）/ Forbidden command patterns (blacklist)
_FORBIDDEN_PATTERNS = (
    "rm -rf /", "rm -rf ~", "dd if=", "mkfs", ":(){ :|:&",
    "fork bomb", "> /dev/sd", "chmod 777 /",
    "shutdown", "reboot", "init 0", "init 6",
    "/etc/shadow", "iptables -F", "kill -9 1",
    "msfconsole",
)

# V8-C02: 只阻止真正危险的注入元字符 / Only block truly dangerous injection metachars
# 允许 |（管道）、&&（条件链）/ Allow | (pipe), && (conditional chain) — core shell features
# 阻止 ; $() 反引号 换行 / Block ; $() backtick newline injection
_SHELL_INJECTION_PATTERN = re.compile(r';|\$\(|`|\n')

# ANSI 转义码剥离正则 / ANSI escape code strip regex — clean terminal color output
_ANSI_STRIP_PATTERN = re.compile(r'\x1b\[[0-9;]*[mGKHJABCDST]')

# Windows 检测 / Windows detection
import sys
_IS_WINDOWS = sys.platform == 'win32'


def _decode_output(data: bytes) -> str:
    """跨平台解码子进程输出 / Cross-platform decode subprocess output.

    Linux/macOS: 通常 UTF-8 / Linux/macOS: typically UTF-8.
    Windows: 控制台常用 GBK/CP936 / Windows: console often GBK/CP936, try multi-encoding fallback.
    """
    if not data:
        return ""
    # 尝试 UTF-8 优先 / Try UTF-8 first
    for encoding in ("utf-8", "gbk", "cp936", "latin-1"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")

# 危险的管道目标 / Dangerous pipe targets
_DANGEROUS_PIPE_TARGETS = re.compile(
    r'\|\s*(ba?sh|python[23]?\s+-c|perl\s+-e|ruby\s+-e|nc\s+-|ncat\s+-|socat\s)',
    re.IGNORECASE,
)


def _get_security():
    """C-08: 延迟初始化 SecurityManager / Lazy init SecurityManager"""
    global _security
    if _security is None:
        from ..security import SecurityManager
        _security = SecurityManager()
    return _security


def _is_command_allowed(command: str) -> tuple[bool, str]:
    """白名单 + 黑名单 + 注入防护 / Allowlist + Blacklist + Injection Protection"""
    cmd_stripped = command.strip()

    # V8-C02: 阻止命令注入元字符 / Block injection metachars (; $() ` newline)
    if _SHELL_INJECTION_PATTERN.search(cmd_stripped):
        return False, "Command injection metacharacters (; $() ` newlines) are not allowed"

    # 危险管道目标检查 / Dangerous pipe target check
    if _DANGEROUS_PIPE_TARGETS.search(cmd_stripped):
        return False, "Piping to shell/script interpreters is forbidden"

    # 黑名单检查 / Blacklist check
    cmd_lower = cmd_stripped.lower()
    for forbidden in _FORBIDDEN_PATTERNS:
        if forbidden.lower() in cmd_lower:
            return False, f"Forbidden pattern: {forbidden}"

    # 白名单检查 / Allowlist check：提取命令的第一个词
    try:
        parts = shlex.split(cmd_stripped, posix=True)
    except ValueError:
        # 含管道时 shlex.split 可能失败 / shlex.split may fail with pipes, but shell=True handles it
        # 尝试取第一个空格前的词 / Try first word before space
        first_word = cmd_stripped.split()[0] if cmd_stripped.split() else ""
        parts = [first_word] if first_word else []

    if not parts:
        return False, "Empty command"

    base_cmd = Path(parts[0]).name
    allowed_bases = set(_ALLOWED_COMMAND_PREFIXES)

    if base_cmd not in allowed_bases:
        return False, f"Command '{base_cmd}' is not in the allowed list. Allowed: {', '.join(sorted(allowed_bases))}"

    return True, "OK"


class ExecTool(BaseTool):
    name = "exec"
    description = "Execute a shell command and return the output"

    async def execute(
        self,
        command: str,
        workdir: str | None = None,
        timeout: int = 30,
    ) -> ToolResult:
        """执行 Shell 命令（带安全检查）/ Execute shell command (with security checks)"""
        # 白名单检查 / Allowlist check
        allowed, reason = _is_command_allowed(command)
        if not allowed:
            return ToolResult(error=f"⛔ 命令被安全模块拦截: {reason}", success=False)

        # 额外的 SecurityManager 检查 / Additional SecurityManager check
        security = _get_security()
        safe, reason = security.check_command(command)
        if not safe:
            return ToolResult(error=f"⛔ 命令被安全模块拦截: {reason}", success=False)

        try:
            cwd = Path(workdir).expanduser() if workdir else Path.cwd()
            # V8-C02: 保留 shell=True / Keep shell=True for pipes (|), chains (&&), vars ($VAR)
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
            # 跨平台编码处理 / Cross-platform encoding: Linux UTF-8, Windows may use GBK/CP936
            output = _decode_output(stdout)
            error = _decode_output(stderr)

            # 剥离 ANSI 转义码 / Strip ANSI codes (terminal colors show as garbage in chat)
            output = _ANSI_STRIP_PATTERN.sub('', output)
            error = _ANSI_STRIP_PATTERN.sub('', error)

            if process.returncode != 0:
                return ToolResult(
                    output=output,
                    error=f"Exit code {process.returncode}: {error}",
                    success=False,
                )
            return ToolResult(output=output + error if error else output)

        except asyncio.TimeoutError:
            try:
                process.kill()
                await process.wait()
            except Exception:
                logger.warning("Failed to kill timed-out process")
            return ToolResult(error=f"Command timed out after {timeout}s", success=False)
        except Exception as e:
            return ToolResult(error=str(e), success=False)

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "exec",
                "description": "Execute a shell command and return stdout/stderr. Use for running scripts, installing packages, file operations, etc.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The shell command to execute"
                        },
                        "workdir": {
                            "type": "string",
                            "description": "Working directory (default: cwd)"
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout in seconds (default: 30)"
                        }
                    },
                    "required": ["command"]
                }
            }
        }
