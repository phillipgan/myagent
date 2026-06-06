"""日历工具 / Calendar Tool — Google Calendar API Integration

支持操作：
Supported Operations:
  - list: 列出未来 N 天的事件 / List events for next N days
  - today: 今天的日程 / Today's schedule
  - search: 按关键词搜索事件 / Search events by keyword
  - create: 创建新事件（需要 OAuth token）/ Create event (requires OAuth token)

认证方式：API Key 或 OAuth access_token。
Auth: API Key (read-only) or OAuth access_token (create events).
Token persisted to workspace/memory/gcal_token.json.
"""

import os
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class CalendarTool(BaseTool):
    name = "calendar"
    description = "Query and manage Google Calendar events"

    def __init__(self):
        self.api_key = os.environ.get("GOOGLE_API_KEY", "")
        self._access_token = ""
        # Token 保存在项目 workspace 目录内 / Token stored in project workspace directory
        _project_root = Path(__file__).resolve().parent.parent.parent
        self._token_file = _project_root / "workspace" / "memory" / "gcal_token.json"

    async def execute(
        self,
        action: str = "list",
        days: int = 7,
        query: str | None = None,
        summary: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> ToolResult:
        """
        日历操作
Calendar operations

        action: list|search|create|today
        days: 查询未来N天 / Query next N days
        query: 搜索关键词 / Search keyword
        summary: 创建事件时的标题 / Event title (for create)
        start_time: ISO格式开始时间 / ISO format start time
        end_time: ISO格式结束时间 / ISO format end time
        """
        if not self.api_key:
            return ToolResult(error="GOOGLE_API_KEY not configured", success=False)

        if action == "today":
            return await self._list_events(days=1)
        elif action == "list":
            return await self._list_events(days=days)
        elif action == "search":
            return await self._search_events(query=query or "")
        elif action == "create":
            if not summary:
                return ToolResult(error="summary is required for create action", success=False)
            return await self._create_event(summary, start_time, end_time)
        else:
            return ToolResult(error=f"Unknown action: {action}", success=False)

    async def _list_events(self, days: int = 7) -> ToolResult:
        """列出即将到来的事件 / List upcoming events"""
        try:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            future = (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                    params={
                        "key": self.api_key,
                        "timeMin": now,
                        "timeMax": future,
                        "singleEvents": "true",
                        "orderBy": "startTime",
                        "maxResults": 20,
                    },
                )
                resp.raise_for_status()  # M-09: 检查 HTTP 状态码 / Check HTTP status code
                data = resp.json()

            if "error" in data:
                return ToolResult(error=f"API error: {data['error'].get('message', '')}", success=False)

            events = data.get("items", [])
            if not events:
                return ToolResult(output=f"No events in the next {days} days.")

            lines = [f"📅 Upcoming events ({days} days):\n"]
            for evt in events:
                start = evt.get("start", {}).get("dateTime", evt.get("start", {}).get("date", ""))
                summary = evt.get("summary", "(No title)")
                lines.append(f"- {start[:16]} | {summary}")

            return ToolResult(output="\n".join(lines))

        except Exception as e:
            return ToolResult(error=str(e), success=False)

    async def _search_events(self, query: str) -> ToolResult:
        """搜索事件 / Search events"""
        try:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            future = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                    params={
                        "key": self.api_key,
                        "timeMin": now,
                        "timeMax": future,
                        "q": query,
                        "singleEvents": "true",
                        "orderBy": "startTime",
                    },
                )
                resp.raise_for_status()  # M-09
                data = resp.json()

            events = data.get("items", [])
            if not events:
                return ToolResult(output=f"No events matching '{query}'.")

            lines = [f"📅 Events matching '{query}':\n"]
            for evt in events:
                start = evt.get("start", {}).get("dateTime", evt.get("start", {}).get("date", ""))
                lines.append(f"- {start[:16]} | {evt.get('summary', '(No title)')}")

            return ToolResult(output="\n".join(lines))

        except Exception as e:
            return ToolResult(error=str(e), success=False)

    async def _create_event(self, summary: str, start_time: str | None,
                            end_time: str | None) -> ToolResult:
        """创建日历事件（需要 OAuth token）/ Create calendar event (requires OAuth token)"""
        if not self._access_token:
            # 尝试从 token 文件加载 / Try to load from token file
            if self._token_file.exists():
                try:
                    token_data = json.loads(self._token_file.read_text())
                    self._access_token = token_data.get("access_token", "")
                except Exception:
                    pass
        if not self._access_token:
            return ToolResult(
                output=f"⛔ Calendar event creation requires OAuth authentication.\n"
                       f"Run: myagent calendar-setup to configure OAuth.\n"
                       f"Event to create: {summary} ({start_time} → {end_time})"
            )
        if not start_time or not end_time:
            return ToolResult(error="start_time and end_time are required for create", success=False)
        try:
            event_body = {
                "summary": summary,
                "start": {"dateTime": start_time},
                "end": {"dateTime": end_time},
            }
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                    params={"key": self.api_key},
                    headers={"Authorization": f"Bearer {self._access_token}"},
                    json=event_body,
                )
                resp.raise_for_status()
                data = resp.json()
            return ToolResult(output=f"✅ Event created: {data.get('summary', summary)}\nLink: {data.get('htmlLink', 'N/A')}")
        except Exception as e:
            return ToolResult(error=f"Failed to create event: {e}", success=False)

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "calendar",
                "description": "Query Google Calendar. Actions: 'list' upcoming events, 'today' today's events, 'search' by keyword, 'create' new event.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["list", "today", "search", "create"],
                            "description": "Action: list, today, search, or create"
                        },
                        "days": {"type": "integer", "description": "Days ahead (default: 7)"},
                        "query": {"type": "string", "description": "Search query"},
                        "summary": {"type": "string", "description": "Event title (for create)"},
                        "start_time": {"type": "string", "description": "Start time ISO format (for create)"},
                        "end_time": {"type": "string", "description": "End time ISO format (for create)"},
                    },
                    "required": ["action"]
                }
            }
        }
