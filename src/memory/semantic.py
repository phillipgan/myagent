"""L3 长期记忆 / L3 Semantic Memory — Vector-based / L3 Long-term Memory — Vector-based Semantic Storage

存储从 L2 巩固而来的长期知识和事实，支持：
Stores long-term knowledge consolidated from L2, supporting:
Stores long-term knowledge and facts consolidated from L2, supporting:
  - 向量相似度检索（sqlite-vec）/ Vector similarity search (sqlite-vec)
  - 全文检索（FTS5）/ Full-text search (FTS5)
  - 重要性排序和时间过滤 / Importance ranking and time filtering

巩固流程 / Consolidation flow:
  L2 episodic → MemoryConsolidator → L3 semantic
  （仅 importance >= 阈值 且 经 LLM 提炼的摘要才进入 L3）/ (Only importance >= threshold + LLM-refined summaries enter L3)

安全设计 / Safety Design:
  - C-09: search_by_vector 添加 LIMIT 子句，避免全表扫描 / Add LIMIT to avoid full table scan
  - H-12: json.loads 包装 try/except / Wrap json.loads in try/except, handle corrupted data / Wrap json.loads in try/except
  - M-28: query_vec_flat 移到循环外 / Move query_vec_flat outside loop
"""

import json
import logging
import struct
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class SemanticMemory:
    """长期语义记忆 — SQLite + sqlite-vec 向量索引 / Long-term Semantic Memory — SQLite + sqlite-vec vector index"""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._embedding_fn = None
        self._init_db()

    def _init_db(self):
        """初始化数据库 / Initialize database"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS semantic (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    content TEXT NOT NULL,
                    summary TEXT DEFAULT '',
                    metadata TEXT DEFAULT '{}',
                    importance REAL DEFAULT 0.5,
                    embedding BLOB
                )
            """)
            try:
                conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS semantic_fts
                    USING fts5(content, summary, content='semantic', content_rowid='id')
                """)
            except sqlite3.OperationalError as e:
                if "no such module" in str(e).lower() or "syntax" in str(e).lower():
                    logger.warning("FTS5 not available, semantic full-text search disabled")
                else:
                    raise
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sem_ts ON semantic(timestamp)")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        logger.info(f"Semantic memory initialized: {self.db_path}")

    def set_embedding_fn(self, fn):
        """设置 embedding 函数 fn(text) -> list[float] / Set embedding function fn(text) -> list[float]"""
        self._embedding_fn = fn

    def _get_embedding(self, text: str) -> Optional[bytes]:
        """获取文本的向量 embedding / Get vector embedding for text"""
        if not self._embedding_fn:
            return None
        try:
            vec = self._embedding_fn(text)
            return struct.pack(f'{len(vec)}f', *vec)
        except Exception as e:
            logger.warning(f"Embedding failed: {e}")
            return None

    def _safe_json_loads(self, raw: str, default=None):
        """H-12: 安全的 JSON 解析，避免损坏数据导致崩溃 / H-12: Safe JSON parsing, handles corrupted data"""
        if not raw:
            return default or {}
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Corrupted metadata, returning default: {raw[:100]}")
            return default or {}

    def store(self, content: str, summary: str = "", metadata: dict | None = None,
             importance: float = 0.7):
        """存储长期记忆（事务安全）/ Store long-term memory (transactional)"""
        now = datetime.now().isoformat()
        meta_str = json.dumps(metadata or {}, ensure_ascii=False)
        embedding = self._get_embedding(content)

        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.execute(
                "INSERT INTO semantic (timestamp, content, summary, metadata, importance, embedding) VALUES (?, ?, ?, ?, ?, ?)",
                (now, content, summary, meta_str, importance, embedding)
            )
            rowid = cursor.lastrowid
            try:
                conn.execute(
                    "INSERT INTO semantic_fts (rowid, content, summary) VALUES (?, ?, ?)",
                    (rowid, content, summary)
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
        """清理 FTS5 特殊字符 / Sanitize FTS5 special characters"""
        import re
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
                SELECT e.id, e.timestamp, e.content, e.summary, e.metadata, e.importance
                FROM semantic_fts f
                JOIN semantic e ON e.id = f.rowid
                WHERE semantic_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (safe_query, limit))

            results = []
            for row in cursor:
                results.append({
                    "id": row[0], "timestamp": row[1], "content": row[2],
                    "summary": row[3], "metadata": self._safe_json_loads(row[4]),
                    "importance": row[5],
                })
        finally:
            conn.close()
        return results

    def search_by_vector(self, query: str, limit: int = 5) -> list[dict]:
        """C-09: 向量相似度搜索 — 使用预筛 LIMIT 避免全表扫描 / Vector similarity search — pre-filter LIMIT to avoid full scan"""
        query_vec = self._get_embedding(query)
        if not query_vec:
            return self.search(query, limit)

        # C-09: 预取 LIMIT * 3 候选 / Prefetch LIMIT * 3 candidates (by importance), not full scan
        candidate_limit = min(limit * 10, 200)
        query_vec_flat = struct.unpack(f'{len(query_vec)//4}f', query_vec)

        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.execute(
                "SELECT id, timestamp, content, summary, metadata, importance, embedding "
                "FROM semantic WHERE embedding IS NOT NULL "
                "ORDER BY importance DESC LIMIT ?",
                (candidate_limit,),
            )

            scored = []
            for row in cursor:
                try:
                    stored_vec = struct.unpack(f'{len(row[6])//4}f', row[6])
                    score = self._cosine_similarity(query_vec_flat, stored_vec)
                    scored.append((score, row))
                except Exception:
                    continue

            scored.sort(key=lambda x: x[0], reverse=True)
            results = []
            for score, row in scored[:limit]:
                results.append({
                    "id": row[0], "timestamp": row[1], "content": row[2],
                    "summary": row[3], "metadata": self._safe_json_loads(row[4]),
                    "importance": row[5], "score": score,
                })
        finally:
            conn.close()
        return results

    @staticmethod
    def _cosine_similarity(a: tuple, b: tuple) -> float:
        """计算余弦相似度 / Calculate cosine similarity"""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def get_all(self, limit: int = 100) -> list[dict]:
        """获取所有长期记忆 / Get all long-term memories"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.execute(
                "SELECT id, timestamp, content, summary, importance FROM semantic ORDER BY importance DESC, timestamp DESC LIMIT ?",
                (limit,)
            )
            results = [{"id": r[0], "timestamp": r[1], "content": r[2], "summary": r[3], "importance": r[4]} for r in cursor]
        finally:
            conn.close()
        return results

    def delete(self, memory_id: int):
        """删除记忆 / Delete memory"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("DELETE FROM semantic WHERE id = ?", (memory_id,))
            try:
                conn.execute("DELETE FROM semantic_fts WHERE rowid = ?", (memory_id,))
            except sqlite3.OperationalError:
                pass
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.warning(f"Failed to delete memory {memory_id}: {e}")
        finally:
            conn.close()
