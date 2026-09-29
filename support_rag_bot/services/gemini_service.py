from __future__ import annotations

import asyncio
import logging
from typing import Any

from google import genai
from pydantic import BaseModel, Field

from support_rag_bot.models import CRMAssistDecision, LLMDecision, RetrievalHit

logger = logging.getLogger(__name__)


class _DecisionSchema(BaseModel):
    action: str = Field(description="One of: answer, clarify, handoff.")
    confidence: float = Field(ge=0.0, le=1.0)
    short_reason: str
    reply_text: str
    citation_ids: list[str]
    missing_information: list[str]


class _CRMAssistSchema(BaseModel):
    client_reply: str
    manager_hint: str
    confidence: float = Field(ge=0.0, le=1.0)
    citation_ids: list[str]
    upsell_product: str | None = None


class GeminiService:
    def __init__(self, api_key: str, generation_model: str, embedding_model: str) -> None:
        self.generation_model = generation_model
        self.embedding_model = embedding_model
        self.client = genai.Client(api_key=api_key)

    async def embed_for_document(self, text: str) -> list[float]:
        instruction = (
            "Represent this support knowledge base article for retrieval in a SaaS support assistant.\n\n"
            f"{text}"
        )
        return await asyncio.to_thread(self._embed_text, instruction)

    async def embed_for_query(self, text: str) -> list[float]:
        instruction = (
            "Represent this incoming support ticket for retrieval against a SaaS knowledge base.\n\n"
            f"{text}"
        )
        return await asyncio.to_thread(self._embed_text, instruction)

    def _embed_text(self, text: str) -> list[float]:
        result = self.client.models.embed_content(model=self.embedding_model, contents=text)

        for attr_name in ("embeddings", "embedding"):
            value = getattr(result, attr_name, None)
            extracted = self._extract_vector(value)
            if extracted:
                return extracted

        if isinstance(result, dict):
            for attr_name in ("embeddings", "embedding"):
                extracted = self._extract_vector(result.get(attr_name))
                if extracted:
                    return extracted

        raise RuntimeError("Gemini embedding response did not contain a usable vector.")

    def _extract_vector(self, value: Any) -> list[float] | None:
        if value is None:
            return None
        if isinstance(value, list):
            if not value:
                return None
            first = value[0]
            if isinstance(first, (int, float)):
                return [float(item) for item in value]
            values = getattr(first, "values", None)
            if values is not None:
                return [float(item) for item in values]
            if isinstance(first, dict):
                nested = first.get("values") or first.get("embedding")
                if nested is not None:
                    return [float(item) for item in nested]
        values = getattr(value, "values", None)
        if values is not None:
            return [float(item) for item in values]
        if isinstance(value, dict):
            nested = value.get("values") or value.get("embedding")
            if nested is not None:
                return [float(item) for item in nested]
        return None

    async def decide_answer(
        self,
        ticket_history: list[str],
        hits: list[RetrievalHit],
        clarification_round: int,
        max_clarification_rounds: int,
    ) -> LLMDecision:
        return await asyncio.to_thread(
            self._decide_answer_sync,
            ticket_history,
            hits,
            clarification_round,
            max_clarification_rounds,
        )

    def _decide_answer_sync(
        self,
        ticket_history: list[str],
        hits: list[RetrievalHit],
        clarification_round: int,
        max_clarification_rounds: int,
    ) -> LLMDecision:
        context = []
        for hit in hits:
            context.append(
                {
                    "citation_id": hit.document.doc_id,
                    "title": hit.document.title,
                    "url": hit.document.url,
                    "score": round(hit.score, 4),
                    "content": hit.document.content,
                }
            )

        dialog = "\n".join(f"User message {index + 1}: {text}" for index, text in enumerate(ticket_history))
        prompt = (
            "You are a SaaS support assistant with strict hallucination control.\n"
            "Decide between exactly three actions: answer, clarify, or handoff.\n"
            "Use answer only when the knowledge base clearly supports a concrete next step or explanation.\n"
            "Use clarify only when one short follow-up from the user would realistically unlock a grounded answer from the provided KB context.\n"
            "Use handoff when the case is likely account-specific, requires manual investigation, depends on logs or internal systems, mentions server-side errors like 5xx, or would still stay ambiguous even after another follow-up.\n"
            "Do not ask a follow-up just to appear helpful. If the next answer still would not let you solve it from the KB, choose handoff.\n"
            "Never invent steps, links, policies, timeframes, permissions, or incident details.\n"
            "Write the final user-facing message in natural Russian, concise and human. No rigid bullet lists unless absolutely necessary.\n"
            "For clarify, ask only the minimum needed, usually one compact follow-up.\n"
            "For answer, include only facts grounded in the KB and return citation_ids for the supporting documents.\n"
            "For clarify or handoff, citation_ids are optional and should be returned only if a link would genuinely help the user right now.\n"
            "Never claim that a human operator is already connected unless the conversation explicitly confirms that external handoff exists.\n"
            f"Current clarification round: {clarification_round}. Maximum allowed: {max_clarification_rounds}.\n\n"
            f"Conversation history:\n{dialog}\n\n"
            f"Knowledge base context:\n{context}"
        )

        response = self.client.models.generate_content(
            model=self.generation_model,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_json_schema": _DecisionSchema.model_json_schema(),
                "temperature": 0.15,
            },
        )
        parsed = _DecisionSchema.model_validate_json(response.text or "{}")
        action = parsed.action.strip().lower()
        if action not in {"answer", "clarify", "handoff"}:
            action = "handoff"
        return LLMDecision(
            action=action,
            confidence=parsed.confidence,
            short_reason=parsed.short_reason,
            reply_text=parsed.reply_text.strip(),
            citation_ids=parsed.citation_ids,
            missing_information=parsed.missing_information,
        )


    async def generate_crm_assist(
        self,
        client_message: str,
        manager_context: str,
        hits: list[RetrievalHit],
    ) -> CRMAssistDecision:
        return await asyncio.to_thread(
            self._generate_crm_assist_sync,
            client_message,
            manager_context,
            hits,
        )

    def _generate_crm_assist_sync(
        self,
        client_message: str,
        manager_context: str,
        hits: list[RetrievalHit],
    ) -> CRMAssistDecision:
        context = [
            {
                "citation_id": hit.document.doc_id,
                "title": hit.document.title,
                "section": hit.document.section,
                "score": round(hit.score, 4),
                "content": hit.document.content,
            }
            for hit in hits
        ]

        prompt = (
            "You are an AI copilot for a sales/support manager working in an AmoCRM chat window.\n"
            "Use only facts from the provided knowledge base context and explicit manager context.\n"
            "Return two clearly different outputs: a client-facing reply and a private manager hint.\n"
            "The client reply must be polite, concise, natural Russian and safe to send as-is.\n"
            "The manager hint must be short and practical. Suggest an upsell only when the client's stated need "
            "clearly maps to a higher plan or capability explicitly documented in the KB.\n"
            "Never invent prices, discounts, deadlines, plan features, guarantees, or policies.\n"
            "If there is no grounded upsell opportunity, say that there is no relevant upsell right now and advise "
            "the manager to solve or clarify the client's issue first.\n"
            "Do not expose the private manager hint in the client reply.\n"
            "citation_ids must contain only ids from the supplied KB context that support the reply/hint.\n"
            "upsell_product must be the exact plan/product name supported by context, or null.\n\n"
            f"Client message:\n{client_message}\n\n"
            f"Manager/CRM context:\n{manager_context or '(not provided)'}\n\n"
            f"Knowledge base context:\n{context}"
        )

        response = self.client.models.generate_content(
            model=self.generation_model,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_json_schema": _CRMAssistSchema.model_json_schema(),
                "temperature": 0.15,
            },
        )
        parsed = _CRMAssistSchema.model_validate_json(response.text or "{}")
        return CRMAssistDecision(
            client_reply=parsed.client_reply.strip(),
            manager_hint=parsed.manager_hint.strip(),
            confidence=parsed.confidence,
            citation_ids=parsed.citation_ids,
            upsell_product=parsed.upsell_product.strip() if parsed.upsell_product else None,
        )
