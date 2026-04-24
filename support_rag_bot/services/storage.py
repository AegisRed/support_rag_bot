from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Iterable

import aiosqlite

from support_rag_bot.models import KBDocument, RetrievalHit, TicketResult


class KnowledgeBaseStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS kb_documents (
                    doc_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    section TEXT NOT NULL,
                    url TEXT NOT NULL,
                    site TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    embedding_json TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS ticket_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    input_text TEXT NOT NULL,
                    auto_resolved INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    answer TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    sources_json TEXT NOT NULL,
                    missing_json TEXT NOT NULL
                )
                """
            )
            await db.commit()

    async def count_documents(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM kb_documents") as cursor:
                row = await cursor.fetchone()
                return int(row[0] or 0)

    async def upsert_documents(self, items: Iterable[tuple[KBDocument, list[float]]]) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            for doc, embedding in items:
                await db.execute(
                    """
                    INSERT INTO kb_documents(doc_id, title, section, url, site, content, tags_json, embedding_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(doc_id) DO UPDATE SET
                        title=excluded.title,
                        section=excluded.section,
                        url=excluded.url,
                        site=excluded.site,
                        content=excluded.content,
                        tags_json=excluded.tags_json,
                        embedding_json=excluded.embedding_json
                    """,
                    (
                        doc.doc_id,
                        doc.title,
                        doc.section,
                        doc.url,
                        doc.site,
                        doc.content,
                        json.dumps(doc.tags, ensure_ascii=False),
                        json.dumps(embedding),
                    ),
                )
            await db.commit()

    async def list_documents(self) -> list[KBDocument]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT doc_id, title, section, url, site, content, tags_json FROM kb_documents ORDER BY title"
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            KBDocument(
                doc_id=row[0],
                title=row[1],
                section=row[2],
                url=row[3],
                site=row[4],
                content=row[5],
                tags=json.loads(row[6]),
            )
            for row in rows
        ]

    async def search(self, query_embedding: list[float], top_k: int = 4) -> list[RetrievalHit]:
        results: list[RetrievalHit] = []
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT doc_id, title, section, url, site, content, tags_json, embedding_json FROM kb_documents"
            ) as cursor:
                async for row in cursor:
                    doc = KBDocument(
                        doc_id=row[0],
                        title=row[1],
                        section=row[2],
                        url=row[3],
                        site=row[4],
                        content=row[5],
                        tags=json.loads(row[6]),
                    )
                    score = cosine_similarity(query_embedding, json.loads(row[7]))
                    results.append(RetrievalHit(document=doc, score=score))
        results.sort(key=lambda item: item.score, reverse=True)
        return results[:top_k]

    async def log_ticket(self, user_id: int, username: str | None, result: TicketResult) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO ticket_logs(
                    created_at, user_id, username, input_text, auto_resolved, confidence, answer, reason, sources_json, missing_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    user_id,
                    username,
                    result.user_text,
                    int(result.auto_resolved),
                    result.confidence,
                    result.reply_text,
                    result.reason,
                    json.dumps(
                        [
                            {"doc_id": hit.document.doc_id, "title": hit.document.title, "url": hit.document.url, "score": round(hit.score, 4)}
                            for hit in result.hits
                        ],
                        ensure_ascii=False,
                    ),
                    json.dumps(result.missing_information, ensure_ascii=False),
                ),
            )
            await db.commit()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
