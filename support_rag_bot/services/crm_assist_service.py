from __future__ import annotations

from support_rag_bot.config import Settings
from support_rag_bot.models import CRMAssistResult
from support_rag_bot.services.gemini_service import GeminiService
from support_rag_bot.services.storage import KnowledgeBaseStore


class CRMAssistService:
    def __init__(
        self,
        store: KnowledgeBaseStore,
        gemini: GeminiService,
        settings: Settings,
    ) -> None:
        self.store = store
        self.gemini = gemini
        self.top_k = settings.top_k
        self.min_similarity_score = settings.min_similarity_score
        self.min_self_confidence = settings.min_self_confidence

    async def assist(self, client_message: str, manager_context: str = "") -> CRMAssistResult:
        client_message = client_message.strip()
        manager_context = manager_context.strip()

        query = client_message
        if manager_context:
            query += f"\nCRM context: {manager_context}"

        query_embedding = await self.gemini.embed_for_query(query)
        hits = await self.store.search(query_embedding, top_k=self.top_k)

        if not hits or hits[0].score < self.min_similarity_score:
            return self._fallback(
                client_message,
                manager_context,
                hits,
                "В базе знаний нет достаточно близкого материала. Нужна ручная проверка или уточнение.",
            )

        decision = await self.gemini.generate_crm_assist(
            client_message=client_message,
            manager_context=manager_context,
            hits=hits,
        )

        valid_ids = {hit.document.doc_id for hit in hits}
        citation_ids = [doc_id for doc_id in decision.citation_ids if doc_id in valid_ids]
        citations_are_valid = bool(citation_ids) and len(citation_ids) == len(decision.citation_ids)

        if (
            not citations_are_valid
            or decision.confidence < self.min_self_confidence
            or not decision.client_reply
            or not decision.manager_hint
        ):
            return self._fallback(
                client_message,
                manager_context,
                hits,
                "Модель не дала достаточно надёжный grounded-ответ по найденным материалам.",
            )

        return CRMAssistResult(
            client_message=client_message,
            manager_context=manager_context,
            client_reply=decision.client_reply,
            manager_hint=decision.manager_hint,
            confidence=decision.confidence,
            hits=hits,
            citation_ids=citation_ids,
            upsell_product=decision.upsell_product,
        )

    def _fallback(
        self,
        client_message: str,
        manager_context: str,
        hits: list,
        reason: str,
    ) -> CRMAssistResult:
        return CRMAssistResult(
            client_message=client_message,
            manager_context=manager_context,
            client_reply=(
                "Спасибо за обращение! Хочу уточнить детали, чтобы дать точный ответ и ничего не пообещать ошибочно. "
                "Подскажите, пожалуйста, какой тариф или функция у вас сейчас используются?"
            ),
            manager_hint=f"Не делать допродажу вслепую. {reason}",
            confidence=0.0,
            hits=hits,
            citation_ids=[],
            upsell_product=None,
        )
