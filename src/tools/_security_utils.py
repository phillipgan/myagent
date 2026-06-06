"""共享安全工具 / Shared Security Utils — Sandbox Check + SSRF Protection（消除 file_read/file_write/file_edit/web_fetch/search_engine 间的代码重复）

修复:
Fixes:
- C-05: 沙箱目录动态获取 cwd() / Dynamic cwd() for sandbox dirs
- C-10: 统一沙箱和 SSRF 逻辑 / Unified sandbox check and SSRF protection, reduce duplication
- H-11: 增强 SSRF 防护 / Enhanced SSRF protection (DNS validation, IPv6, full private ranges)
"""

import ipaddress
import logging
import socket
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────
# 文件沙箱 / File Sandbox
# ────────────────────────────────────────────────────────

# 静态沙箱目录（模块加载时确定）/ Static sandbox dirs (determined at module load)
# 包含项目内 workspace 目录代替 ~/.myagent / Includes project-local workspace instead of ~/.myagent
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # myagent 项目根目录 / Project root
_STATIC_SANDBOX_DIRS = [
    _PROJECT_ROOT / "workspace",   # myagent 工作目录 / myagent workspace
    _PROJECT_ROOT,                  # myagent 项目根本身 / Project root itself
    Path.home() / "AIspace",
    Path.home() / ".openclaw",
]


def get_sandbox_dirs() -> list[Path]:
    """C-05: 动态获取沙箱目录列表 / Get sandbox dirs dynamically (includes cwd)"""
    dirs = list(_STATIC_SANDBOX_DIRS)
    try:
        cwd = Path.cwd()
        if cwd not in dirs:
            dirs.append(cwd)
    except Exception:
        pass
    return dirs


def check_sandbox(file_path: Path) -> tuple[bool, str]:
    """检查路径是否在允许的沙箱目录内 / Check if path is within allowed sandbox dirs"""
    try:
        resolved = file_path.resolve()
    except (ValueError, OSError) as e:
        return False, f"Invalid path: {e}"

    for base in get_sandbox_dirs():
        try:
            base_resolved = base.resolve()
            if resolved.is_relative_to(base_resolved):
                return True, ""
        except (ValueError, OSError):
            continue
    return False, f"Path outside allowed directories: {file_path}"


# ────────────────────────────────────────────────────────
# SSRF 防护 / SSRF Protection
# ────────────────────────────────────────────────────────

# 已知的元数据/内网主机名 / Known metadata/intranet hostnames
_BLOCKED_HOSTNAMES = frozenset({
    "169.254.169.254",       # AWS/GCP/Azure metadata
    "metadata.google.internal",
    "localhost", "127.0.0.1", "0.0.0.0",
    "::1", "0000::1",
    "[::1]",
})

# IPv4 私有网段 / IPv4 private ranges (RFC 1918 + RFC 6598 + loopback + link-local)
_PRIVATE_IPV4_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),     # Carrier-grade NAT (RFC 6598)
    ipaddress.ip_network("198.18.0.0/15"),     # Benchmark testing (RFC 2544)
    ipaddress.ip_network("0.0.0.0/8"),         # "This" network
]

# IPv6 私有/保留网段 / IPv6 private/reserved ranges
_PRIVATE_IPV6_NETWORKS = [
    ipaddress.ip_network("::1/128"),           # Loopback
    ipaddress.ip_network("fc00::/7"),          # Unique local (RFC 4193)
    ipaddress.ip_network("fe80::/10"),         # Link-local
    ipaddress.ip_network("::ffff:0:0/96"),     # IPv4-mapped IPv6
    ipaddress.ip_network("100::/64"),          # Discard-only (RFC 6666)
]


def _is_private_ip(ip_str: str) -> bool:
    """H-11: 检查 IP 是否为私有/保留 / Check if IP is private/reserved (IPv4 + IPv6)"""
    try:
        ip = ipaddress.ip_address(ip_str)
        if ip.version == 4:
            return any(ip in net for net in _PRIVATE_IPV4_NETWORKS)
        else:
            return any(ip in net for net in _PRIVATE_IPV6_NETWORKS)
    except ValueError:
        return False


def _resolve_host(host: str) -> list[str]:
    """解析主机名到 IP 地址列表 / Resolve hostname to IP address list"""
    try:
        results = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        return list({r[4][0] for r in results})
    except (socket.gaierror, OSError):
        return []


def is_safe_url(url: str) -> tuple[bool, str]:
    """H-11: 增强的 SSRF 防护检查 / Enhanced SSRF Protection Check

    - 支持完整的 IPv4 私有地址段 / Full IPv4 private range support
    - 支持 IPv6（含 IPv4-mapped）/ IPv6 support (including IPv4-mapped)
    - DNS 解析后验证 IP / Post-DNS IP validation (prevent DNS rebinding)
    - 阻止元数据端点 / Block metadata endpoints
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL"

    if parsed.scheme not in ("http", "https"):
        return False, f"Unsupported scheme: {parsed.scheme}"

    host = parsed.hostname
    if not host:
        return False, "No hostname in URL"

    # 去掉 IPv6 方括号 / Strip IPv6 brackets
    host_clean = host.strip("[]")

    # 检查已知危险主机名 / Check known dangerous hostnames
    if host_clean.lower() in _BLOCKED_HOSTNAMES:
        return False, f"Blocked host: {host}"

    # 直接检查 IP 地址格式 / Check IP address format directly
    if _is_private_ip(host_clean):
        return False, f"Blocked private IP: {host}"

    # DNS 解析后检查 IP / Check resolved IPs after DNS lookup
    # 只在 host 不是 IP 时做 DNS 解析 / Only DNS resolve if host is not an IP
    try:
        ipaddress.ip_address(host_clean)
    except ValueError:
        # host 是域名，做 DNS 解析 / Host is domain, do DNS lookup
        resolved_ips = _resolve_host(host_clean)
        for rip in resolved_ips:
            if _is_private_ip(rip):
                return False, f"Host resolves to private IP: {host} -> {rip}"

    return True, ""
