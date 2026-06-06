"""L2 短期记忆 / L2 Episodic Memory — 基于 SQLite + FTS5 的近期事件存储

存储每次对话的摘要（用户消息 + 助手回复 + 工具调用），
Stores conversation summaries (user msg + assistant reply + tool calls),
支持全文检索和按时间/重要性查询。
Supports full-text search and time/importance queries.

生命周期：
Lifecycle:
  - 默认保留 7 天 / Default: 7-day retention
  - 高重要性事件永久保留 / High-importance (importance > 0.7) kept permanently
  - 超期低重要性自动清理 / Expired low-importance auto-cleaned

安全设计:
Safety Design:
  - H-12: json.loads 包装 try/except / Wrap json.loads in try/except, handle corrupted data
"""

import json
import logging
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class EpisodicMemory:
    """短期记忆 — 最近7天的事件和对话摘要 / Episodic Memory — Recent 7 days"""

    def __init__(self, db_path: str, retention_days: int = 7):
        self.db_path = Path(db_path)
        self.retention_days = retention_days
        self._init_db()

    def _init_db(self):
        """初始化 SQLite + FTS5 / Initialize SQLite + FTS5"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episodic (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    importance REAL DEFAULT 0.5
                )
            """)
            try:
                conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS episodic_fts
                    USING fts5(content, metadata, content='episodic', content_rowid='id')
                """)
            except sqlite3.OperationalError as e:
                if "no such module" in str(e):
                    logger.warning("FTS5 not available, full-text search disabled")
                else:
                    raise
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON episodic(timestamp)
            """)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        logger.info(f"Episodic memory initialized: {self.db_path}")

    def _safe_json_loads(self, raw: str, default=None):
        """H-12: 安全的 JSON 解析 / Safe JSON parsing"""
        if not raw:
            return default or {}
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Corrupted metadata, returning default: {raw[:100]}")
            return default or {}

    def store(self, content: str, metadata: dict | None = None, importance: float = 0.5):
        """存储一条记忆（事务安全）/ Store a memory entry (transactional)"""
        now = datetime.now().isoformat()
        meta_str = json.dumps(metadata or {}, ensure_ascii=False)

        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.execute(
                "INSERT INTO episodic (timestamp, content, metadata, importance) VALUES (?, ?, ?, ?)",
                (now, content, meta_str, importance)
            )
            rowid = cursor.lastrowid
            try:
                conn.execute(
                    "INSERT INTO episodic_fts (rowid, content, metadata) VALUES (?, ?, ?)",
                    (rowid, content, meta_str)
                )
            except sqlite3.OperationalError:
                pass  # FTS5 may not be available
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _sanitize_fts(query: str) -> str:
        """清理 FTS5 特殊字符 / Sanitize FTS5 special characters, prevent syntax errors"""
        cleaned = re.sub(r'["*:^(){}\[\]\\]', ' ', query)
        cleaned = re.sub(r'\b(AND|OR|NOT|NEAR)\b', ' ', cleaned, flags=re.IGNORECASE)
        cleaned = ' '.join(cleaned.split())
        return cleaned or query

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """FTS5 全文搜索 / FTS5 full-text search"""
        safe_query = self._sanitize_fts(query)
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.execute("""
                SELECT e.id, e.timestamp, e.content, e.metadata, e.importance,
                       rank
                FROM episodic_fts f
                JOIN episodic e ON e.id = f.rowid
                WHERE episodic_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (safe_query, limit))

            results = []
            for row in cursor:
                results.append({
                    "id": row[0],
                    "timestamp": row[1],
                    "content": row[2],
                    "metadata": self._safe_json_loads(row[3]),
                    "importance": row[4],
                })
        finally:
            conn.close()
        return results

    def get_recent(self, hours: int = 24, limit: int = 10) -> list[dict]:
        """获取最近N小时的记忆 / Get memories from last N hours"""
        since = (datetime.now() - timedelta(hours=hours)).isoformat()

        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.execute("""
                SELECT id, timestamp, content, metadata, importance
                FROM episodic
                WHERE timestamp > ?
                ORDER BY importance DESC, timestamp DESC
                LIMIT ?
            """, (since, limit))

            results = []
            for row in cursor:
                results.append({
                    "id": row[0],
                    "timestamp": row[1],
                    "content": row[2],
                    "metadata": self._safe_json_loads(row[3]),
                    "importance": row[4],
                })
        finally:
            conn.close()
        return results

    def cleanup(self):
        """清理过期记忆 / Clean up expired memories"""
        cutoff = (datetime.now() - timedelta(days=self.retention_days)).isoformat()
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.execute(
                "SELECT id FROM episodic WHERE timestamp < ? AND importance <= 0.7",
                (cutoff,),
            )
            ids_to_delete = [row[0] for row in cursor]

            if ids_to_delete:
                placeholders = ",".join("?" * len(ids_to_delete))
                conn.execute(
                    f"DELETE FROM episodic WHERE id IN ({placeholders})",
                    ids_to_delete,
                )
                try:
                    conn.execute(
                        f"DELETE FROM episodic_fts WHERE rowid IN ({placeholders})",
                        ids_to_delete,
                    )
                except Exception as e:
                    logger.warning(f"FTS5 cleanup skipped: {e}")
                conn.commit()
                logger.info(f"Cleaned up {len(ids_to_delete)} expired episodic memories (FTS5 synced)")
        except Exception as e:
            conn.rollback()
            logger.warning(f"Episodic cleanup failed: {e}")
        finally:
            conn.close()

    def get_consolidation_candidates(self, threshold: float = 0.6) -> list[dict]:
        """获取值得巩固到长期记忆的候选 / Get candidates worth consolidating to L3"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.execute("""
                SELECT id, timestamp, content, metadata, importance
                FROM episodic
                WHERE importance >= ?
                ORDER BY importance DESC, timestamp DESC
                LIMIT 50
            """, (threshold,))

            results = []
            for row in cursor:
                results.append({
                    "id": row[0],
                    "timestamp": row[1],
                    "content": row[2],
                    "metadata": self._safe_json_loads(row[3]),
                    "importance": row[4],
                })
        finally:
            conn.close()
        return results
