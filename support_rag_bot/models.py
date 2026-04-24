from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal

from pydantic import BaseModel, Field


@dataclass(slots=True)
class KBDocument:
    doc_id: str
    title: str
    section: str
    url: str
    site: str
    content: str
    tags: List[str]


@dataclass(slots=True)
class RetrievalHit:
    document: KBDocument
    score: float


class LLMDecision(BaseModel):
    action: Literal["answer", "clarify", "handoff"] = Field(
        description="answer when the KB clearly supports a reply, clarify when one targeted follow-up could realistically unlock a grounded answer, handoff when a human should take over."
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Model confidence from 0 to 1.")
    short_reason: str = Field(description="Very short reason for the decision.")
    reply_text: str = Field(description="Natural Russian reply to send to the user for the chosen action.")
    citation_ids: list[str] = Field(default_factory=list, description="Only source ids from the provided context.")
    missing_information: list[str] = Field(
        default_factory=list,
        description="What is missing if the assistant should clarify or hand off.",
    )


@dataclass(slots=True)
class TicketResult:
    user_text: str
    mode: Literal["answer", "clarify", "handoff"]
    reply_text: str
    confidence: float
    reason: str
    hits: list[RetrievalHit]
    missing_information: list[str]
    link_doc_ids: list[str]

    @property
    def auto_resolved(self) -> bool:
        return self.mode == "answer"
