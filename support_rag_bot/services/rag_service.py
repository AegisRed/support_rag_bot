from __future__ import annotations

from html import escape

from support_rag_bot.config import Settings
from support_rag_bot.models import KBDocument, TicketResult
from support_rag_bot.services.gemini_service import GeminiService
from support_rag_bot.services.seed import build_seed_documents
from support_rag_bot.services.storage import KnowledgeBaseStore


class RAGService:
    def __init__(
        self,
        store: KnowledgeBaseStore,
        gemini: GeminiService,
        settings: Settings,
    ) -> None:
        self.store = store
        self.gemini = gemini
        self.settings = settings
        self.source_sites = settings.source_sites
        self.top_k = settings.top_k
        self.min_similarity_score = settings.min_similarity_score
        self.min_self_confidence = settings.min_self_confidence
        self.max_clarification_rounds = settings.max_clarification_rounds

    async def bootstrap(self) -> None:
        await self.store.init()
        if await self.store.count_documents() > 0:
            return
        docs = build_seed_documents(self.source_sites)
        payload: list[tuple[KBDocument, list[float]]] = []
        for doc in docs:
            embedding = await self.gemini.embed_for_document(f"{doc.title}\n{doc.section}\n{doc.content}")
            payload.append((doc, embedding))
        await self.store.upsert_documents(payload)

    async def reindex_seed_documents(self) -> int:
        docs = build_seed_documents(self.source_sites)
        payload: list[tuple[KBDocument, list[float]]] = []
        for doc in docs:
            embedding = await self.gemini.embed_for_document(f"{doc.title}\n{doc.section}\n{doc.content}")
            payload.append((doc, embedding))
        await self.store.upsert_documents(payload)
        return len(payload)

    async def list_documents(self) -> list[KBDocument]:
        return await self.store.list_documents()

    async def answer_ticket(self, ticket_history: list[str], clarification_round: int = 0) -> TicketResult:
        query_text = "\n".join(ticket_history).strip()
        query_embedding = await self.gemini.embed_for_query(query_text)
        hits = await self.store.search(query_embedding, top_k=self.top_k)

        if not hits:
            if clarification_round < self.max_clarification_rounds:
                return TicketResult(
                    user_text=query_text,
                    mode="clarify",
                    reply_text=self._fallback_clarify_message(ticket_history),
                    confidence=0.0,
                    reason="В базе знаний пока не нашлось достаточно близких материалов.",
                    hits=[],
                    missing_information=["Нужно уточнить симптомы и шаг, на котором возникает проблема."],
                    link_doc_ids=[],
                )
            return TicketResult(
                user_text=query_text,
                mode="handoff",
                reply_text=(
                    "Пока не вижу надёжной опоры в базе знаний, чтобы не придумывать ответ. "
                    "Тут лучше передать кейс оператору. Я больше не буду пытаться автоответить по этому тикету. "
                    "Если хотите, можете дописать детали сюда, а завершить тикет можно командой /exitticket."
                ),
                confidence=0.0,
                reason="В базе знаний нет надёжной опоры для ответа.",
                hits=[],
                missing_information=["knowledge_base_empty"],
                link_doc_ids=[],
            )

        top_score = hits[0].score
        decision = await self.gemini.decide_answer(
            ticket_history=ticket_history,
            hits=hits,
            clarification_round=clarification_round,
            max_clarification_rounds=self.max_clarification_rounds,
        )

        valid_citation_ids = {hit.document.doc_id for hit in hits}
        link_doc_ids = [doc_id for doc_id in decision.citation_ids if doc_id in valid_citation_ids]
        citations_are_valid = bool(link_doc_ids) and len(link_doc_ids) == len(decision.citation_ids)
        can_auto_answer = all(
            [
                decision.action == "answer",
                top_score >= self.min_similarity_score,
                decision.confidence >= self.min_self_confidence,
                citations_are_valid,
                bool(decision.reply_text.strip()),
            ]
        )

        if can_auto_answer:
            return TicketResult(
                user_text=query_text,
                mode="answer",
                reply_text=decision.reply_text.strip(),
                confidence=decision.confidence,
                reason=decision.short_reason,
                hits=hits,
                missing_information=decision.missing_information,
                link_doc_ids=link_doc_ids,
            )

        should_try_clarify = (
            decision.action == "clarify"
            and clarification_round < self.max_clarification_rounds
            and self._can_one_more_reply_help(decision.missing_information, hits)
        )

        if should_try_clarify:
            clarify_text = decision.reply_text.strip() or self._fallback_clarify_message(ticket_history)
            return TicketResult(
                user_text=query_text,
                mode="clarify",
                reply_text=clarify_text,
                confidence=max(decision.confidence, top_score),
                reason=decision.short_reason or "Нужно уточнить пару деталей, чтобы не гадать.",
                hits=hits,
                missing_information=decision.missing_information,
                link_doc_ids=link_doc_ids,
            )

        return TicketResult(
            user_text=query_text,
            mode="handoff",
            reply_text=(
                decision.reply_text.strip()
                or "Похоже, здесь уже нужен оператор. Я не буду дальше гадать по базе знаний. "
                "Если хотите, можете прислать сюда дополнительные детали, а завершить тикет — /exitticket."
            ),
            confidence=max(decision.confidence, top_score),
            reason=decision.short_reason or "После уточнений всё ещё нужен ручной разбор кейса.",
            hits=hits,
            missing_information=decision.missing_information,
            link_doc_ids=link_doc_ids,
        )

    def _can_one_more_reply_help(self, missing_information: list[str], hits: list) -> bool:
        if not missing_information:
            return False
        if not hits:
            return True
        top_score = hits[0].score
        if top_score < max(0.55, self.min_similarity_score - 0.15):
            return False
        latest_content = " ".join(item.document.content.lower() for item in hits[:2])
        if any(marker in latest_content for marker in ("manual review", "contact support", "operator", "support team")):
            return False
        return True

    def _fallback_clarify_message(self, ticket_history: list[str]) -> str:
        latest = ticket_history[-1].lower() if ticket_history else ""
        if any(code in latest for code in ("500", "502", "503", "504")):
            return (
                "Понял. Чтобы не гадать, уточню только одно: эта ошибка появляется сразу после ввода логина и пароля "
                "или уже после нажатия кнопки входа?"
            )
        if any(token in latest for token in ("вход", "авториза", "логин", "учет")):
            return "Понял. Подскажи, пожалуйста, что именно пишет система при входе или на каком шаге всё ломается?"
        return "Понял. Подскажи, пожалуйста, на каком шаге возникает проблема и есть ли точный текст ошибки?"


def _pick_documents_by_ids(result: TicketResult) -> list[KBDocument]:
    if not result.link_doc_ids:
        return []
    documents: list[KBDocument] = []
    wanted = set(result.link_doc_ids)
    for hit in result.hits:
        if hit.document.doc_id in wanted:
            documents.append(hit.document)
    return documents


def _pick_default_documents(result: TicketResult, limit: int = 2) -> list[KBDocument]:
    return [hit.document for hit in result.hits[:limit]]


def _render_links_sentence(documents: list[KBDocument]) -> str:
    if not documents:
        return ""
    rendered = [f'<a href="{escape(doc.url)}">{escape(doc.title)}</a>' for doc in documents]
    if len(rendered) == 1:
        return f"\n\nЕсли пригодится, вот материал по теме: {rendered[0]}."
    return f"\n\nЕсли пригодится, вот материалы по теме: {', '.join(rendered[:-1])} и {rendered[-1]}."


def format_ticket_result(
    result: TicketResult,
    settings: Settings,
    shown_doc_ids: set[str] | None = None,
) -> tuple[str, list[str]]:
    shown_doc_ids = shown_doc_ids or set()
    details_suffix = ""
    if settings.show_decision_details:
        details_suffix = (
            f"\n\n<b>Диагностика</b>\n"
            f"Уверенность: {result.confidence:.2f}\n"
            f"Причина: {escape(result.reason)}"
        )

    candidate_docs = _pick_documents_by_ids(result)
    if not candidate_docs and result.mode == "clarify" and not shown_doc_ids:
        candidate_docs = _pick_default_documents(result)
    elif not candidate_docs and result.mode == "answer":
        candidate_docs = _pick_default_documents(result)

    fresh_docs = [doc for doc in candidate_docs if doc.doc_id not in shown_doc_ids][:2]
    text = escape(result.reply_text)
    if fresh_docs:
        text += _render_links_sentence(fresh_docs)
    text += details_suffix
    return text, [doc.doc_id for doc in fresh_docs]
