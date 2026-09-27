"""Hybrid RAG: SQL/exact + text search + vector → fusion → rerank → grounded answer.

Structured fields remain SQL-primary. LLM (when configured) answers only from retrieved context.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.permissions import PermissionCode, require_permission
from app.services.rag import RagService, RetrievalHit
from app.services.search import SearchEntityType, SearchHit, SearchService

log = get_logger(__name__)


@dataclass
class AnalyzedQuery:
    raw: str
    intent: str  # lookup | semantic | hybrid
    vin: str | None = None
    case_number: str | None = None
    stock_number: str | None = None
    brand: str | None = None
    model: str | None = None
    entity_types: list[str] = field(default_factory=list)
    free_text: str = ""
    wants_status: bool = False
    wants_policy: bool = False


@dataclass
class FusedHit:
    entity_type: str
    entity_id: UUID
    title: str
    content: str
    sources: list[str]  # sql | text | vector
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HybridResult:
    request_id: str
    query: AnalyzedQuery
    hits: list[FusedHit]
    context: str
    answer: str
    answer_mode: str = "extractive"  # extractive | llm


class QueryAnalyzer:
    """Deterministic query analysis — no LLM."""

    VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{11,17})\b", re.I)
    CASE_RE = re.compile(r"\b(C-\d{3,})\b", re.I)
    STOCK_RE = re.compile(r"#\s*(\d+)|(?:stock|شماره)\s*[:=]?\s*(\d+)", re.I)

    BRANDS = (
        "toyota",
        "hyundai",
        "peugeot",
        "kia",
        "bmw",
        "mercedes",
        "تویوتا",
        "هیوندای",
        "هیوندا",
        "پژو",
        "کیا",
    )
    MODELS = (
        "camry",
        "elantra",
        "tucson",
        "sportage",
        "cerato",
        "i20",
        "207",
        "کمری",
        "النترا",
        "توسان",
    )

    # Persian names must be mapped to the Latin values stored in inventory.
    CANONICAL = {
        "تویوتا": "Toyota",
        "هیوندای": "Hyundai",
        "هیوندا": "Hyundai",
        "پژو": "Peugeot",
        "کیا": "Kia",
        "کمری": "Camry",
        "النترا": "Elantra",
        "توسان": "Tucson",
    }
    DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

    def analyze(self, query: str, entity_types: list[str] | None = None) -> AnalyzedQuery:
        raw = (query or "").strip().translate(self.DIGITS)
        lower = raw.lower()

        vin = None
        m = self.VIN_RE.search(raw)
        if m and self._looks_like_vin(m.group(1)):
            vin = m.group(1).upper()

        case_number = None
        cm = self.CASE_RE.search(raw)
        if cm:
            case_number = cm.group(1).upper()

        stock_number = None
        sm = self.STOCK_RE.search(raw)
        if sm:
            stock_number = sm.group(1) or sm.group(2)

        brand_raw = next((b for b in self.BRANDS if b in lower or b in raw), None)
        model_raw = next((md for md in self.MODELS if md in lower or md in raw), None)
        brand = self._canonical(brand_raw)
        model = self._canonical(model_raw)
        year_m = re.search(r"(?:19|20)\d{2}", raw)

        wants_status = any(
            w in raw or w in lower
            for w in ("وضعیت", "status", "state", "کجاست", "موجود", "چطوره", "چه خبر", "داره", "دارد")
        )
        wants_policy = any(
            w in lower or w in raw
            for w in (
                "rule",
                "policy",
                "sop",
                "قانون",
                "قوانین",
                "سیاست",
                "دستورالعمل",
                "آیین",
                "دانشنامه",
            )
        )

        types = list(entity_types) if entity_types else []
        if not types:
            if brand or model or vin or stock_number or any(
                w in lower or w in raw
                for w in ("vehicle", "ماشین", "خودرو", "vin", "موجودی", "انبار", "camry", "کمری")
            ):
                types.append("vehicle")
            if any(w in lower or w in raw for w in ("case", "پرونده", "c-")) or (
                "پیگیری" in raw and not (brand or model or wants_status)
            ):
                types.append("case")
            if any(
                w in lower or w in raw
                for w in ("reza", "sara", "علی", "رضا", "سارا", "employee", "کارمند", "نفر")
            ):
                types.append("user")
            if any(w in lower or w in raw for w in ("work", "فروش", "task", "کار", "وظیفه", "تسک", "پیگیری مشتری")):
                types.append("work_item")
            if wants_policy:
                types.append("document")

            vehicle_focus = bool(brand or model or vin or stock_number) and not any(
                t in types for t in ("work_item", "user", "case")
            )
            if brand or model or vin or stock_number:
                if "vehicle" not in types:
                    types.append("vehicle")
            if vehicle_focus or (wants_status and "vehicle" in types and not wants_policy):
                # Status-of-car questions: don't dilute with KB
                types = [t for t in types if t != "document"]
            elif not types:
                types = ["vehicle", "case", "work_item", "user", "document"]
            elif not wants_policy and "document" not in types and len(raw.split()) >= 4:
                types.append("document")

        if vin or case_number or stock_number or brand or model:
            intent = "lookup"
        elif len(raw.split()) >= 3 or any(
            q in raw for q in ("؟", "?", "چیست", "چطور", "چی", "what", "how", "why", "وضعیت")
        ):
            intent = "hybrid"
        else:
            intent = "semantic"

        free = raw
        if brand or model:
            bits = [x for x in (brand, model, year_m.group(0) if year_m else None) if x]
            free = " ".join(bits)

        return AnalyzedQuery(
            raw=raw,
            intent=intent,
            vin=vin,
            case_number=case_number,
            stock_number=stock_number,
            brand=brand,
            model=model,
            entity_types=types,
            free_text=free or raw,
            wants_status=wants_status,
            wants_policy=wants_policy,
        )

    @classmethod
    def _canonical(cls, name: str | None) -> str | None:
        if not name:
            return None
        if name in cls.CANONICAL:
            return cls.CANONICAL[name]
        return name.title() if name.isascii() else name

    @staticmethod
    def _looks_like_vin(value: str) -> bool:
        cleaned = value.strip().upper()
        return len(cleaned) >= 11 and cleaned.isalnum()


def reciprocal_rank_fusion(
    ranked_lists: list[list[tuple[str, UUID, float]]],
    *,
    k: int = 60,
) -> dict[tuple[str, UUID], float]:
    """RRF over (entity_type, entity_id) keys. ranked_lists contain (type, id, score)."""
    scores: dict[tuple[str, UUID], float] = {}
    for ranked in ranked_lists:
        for rank, (etype, eid, _score) in enumerate(ranked, start=1):
            key = (etype, eid)
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
    return scores


class HybridRagService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.analyzer = QueryAnalyzer()
        self.search = SearchService(db)
        self.rag = RagService(db)

    async def run(
        self,
        *,
        organization_id: UUID,
        query: str,
        actor_permissions: set[str],
        entity_types: list[str] | None = None,
        branch_id: UUID | None = None,
        top_k: int = 8,
        context_char_limit: int = 4000,
    ) -> HybridResult:
        require_permission(actor_permissions, PermissionCode.RAG_READ)
        request_id = str(uuid.uuid4())
        analyzed = self.analyzer.analyze(query, entity_types)

        sql_hits: list[SearchHit] = []
        can_search = (
            PermissionCode.SEARCH in actor_permissions
            or PermissionCode.ORG_ADMIN in actor_permissions
        )
        if can_search:
            search_types = []
            for t in analyzed.entity_types:
                try:
                    search_types.append(SearchEntityType(t))
                except ValueError:
                    continue
            sql_hits = await self.search.search(
                organization_id=organization_id,
                actor_permissions=actor_permissions | {PermissionCode.SEARCH},
                q=analyzed.free_text if not (analyzed.brand or analyzed.model) else None,
                types=search_types or None,
                branch_id=branch_id,
                vin=analyzed.vin,
                case_number=analyzed.case_number,
                stock_number=analyzed.stock_number,
                brand=analyzed.brand,
                model=analyzed.model,
                limit=20,
            )

        # Direct inventory fallback when brand/model known but SQL channel empty/unavailable
        if (analyzed.brand or analyzed.model) and not any(
            h.entity_type == "vehicle" for h in sql_hits
        ):
            if (
                PermissionCode.INVENTORY_READ in actor_permissions
                or PermissionCode.ORG_ADMIN in actor_permissions
                or PermissionCode.SEARCH in actor_permissions
            ):
                from app.services.inventory import InventoryService

                vehicles = await InventoryService(self.db).search_vehicles(
                    organization_id,
                    brand=analyzed.brand,
                    model=analyzed.model,
                    q=analyzed.model or analyzed.brand,
                )
                for v in vehicles[:20]:
                    sql_hits.append(
                        SearchHit(
                            entity_type=SearchEntityType.VEHICLE,
                            entity_id=v.id,
                            title=f"{v.brand} {v.model}"
                            + (f" #{v.stock_number}" if v.stock_number else ""),
                            subtitle=f"VIN {v.vin} · {v.status.value}"
                            + (f" · {v.year}" if v.year else ""),
                            score=8.0,
                            match_kind="text",
                            metadata={
                                "vin": v.vin,
                                "stock_number": v.stock_number,
                                "status": v.status.value,
                                "year": v.year,
                                "brand": v.brand,
                                "model": v.model,
                            },
                        )
                    )

        vector_hits: list[RetrievalHit] = []
        if analyzed.intent in ("semantic", "hybrid", "lookup"):
            vec_types = list(analyzed.entity_types)
            vec_query = analyzed.free_text if (analyzed.brand or analyzed.model) else analyzed.raw
            vector_hits = await self.rag.semantic_search(
                organization_id=organization_id,
                query=vec_query,
                actor_permissions=actor_permissions,
                entity_types=vec_types,
                branch_id=branch_id,
                top_k=20,
                min_score=0.01,
            )

        exact_ranked = [
            (h.entity_type, h.entity_id, h.score)
            for h in sorted(sql_hits, key=lambda x: x.score, reverse=True)
            if h.match_kind == "exact"
        ]
        text_ranked = [
            (h.entity_type, h.entity_id, h.score)
            for h in sorted(sql_hits, key=lambda x: x.score, reverse=True)
            if h.match_kind in ("text", "filter")
        ]
        sql_ranked = [
            (h.entity_type, h.entity_id, h.score)
            for h in sorted(sql_hits, key=lambda x: x.score, reverse=True)
        ]
        vector_ranked = [
            (h.entity_type, h.entity_id, h.score)
            for h in sorted(vector_hits, key=lambda x: x.score, reverse=True)
        ]

        lists = [lst for lst in (exact_ranked, text_ranked or sql_ranked, vector_ranked) if lst]
        rrf = reciprocal_rank_fusion(lists) if lists else {}

        by_key: dict[tuple[str, UUID], FusedHit] = {}
        for h in sql_hits:
            key = (h.entity_type, h.entity_id)
            sources = ["sql"]
            if h.match_kind == "exact":
                sources = ["sql", "exact"]
            elif h.match_kind == "text":
                sources = ["sql", "text"]
            by_key[key] = FusedHit(
                entity_type=h.entity_type,
                entity_id=h.entity_id,
                title=h.title,
                content=h.subtitle or h.title,
                sources=sources,
                score=rrf.get(key, h.score / 10.0),
                metadata={**h.metadata, "match_kind": h.match_kind},
            )
        for h in vector_hits:
            key = (h.entity_type, h.entity_id)
            if key in by_key:
                if "vector" not in by_key[key].sources:
                    by_key[key].sources.append("vector")
                by_key[key].score = rrf.get(key, by_key[key].score)
                if len(h.content) > len(by_key[key].content):
                    by_key[key].content = h.content
            else:
                title = str(h.metadata.get("title") or h.content[:80])
                by_key[key] = FusedHit(
                    entity_type=h.entity_type,
                    entity_id=h.entity_id,
                    title=title,
                    content=h.content,
                    sources=["vector"],
                    score=rrf.get(key, h.score),
                    metadata=h.metadata,
                )

        fused = list(by_key.values())
        fused = self._rerank(fused, analyzed)
        fused = fused[: max(1, min(top_k, 20))]

        context = self._build_context(fused, limit=context_char_limit)
        answer, answer_mode = await self._answer(analyzed, fused, context)

        for h in fused:
            h.metadata["request_id"] = request_id

        return HybridResult(
            request_id=request_id,
            query=analyzed,
            hits=fused,
            context=context,
            answer=answer,
            answer_mode=answer_mode,
        )

    def _rerank(self, hits: list[FusedHit], analyzed: AnalyzedQuery) -> list[FusedHit]:
        q = (analyzed.raw or "").lower()
        for h in hits:
            boost = 0.0
            blob = f"{h.title} {h.content}".lower()
            if "exact" in h.sources:
                boost += 0.5
            if analyzed.vin and h.metadata.get("vin") == analyzed.vin:
                boost += 1.5
            if analyzed.stock_number and str(h.metadata.get("stock_number") or "") == analyzed.stock_number:
                boost += 1.2
            if analyzed.case_number and h.title.upper() == analyzed.case_number:
                boost += 1.0
            if analyzed.brand and analyzed.brand.lower() in blob:
                boost += 1.2
                if h.entity_type == "vehicle":
                    boost += 0.8
            if analyzed.model and analyzed.model.lower() in blob:
                boost += 1.4
                if h.entity_type == "vehicle":
                    boost += 1.0
            if analyzed.wants_status and h.entity_type == "vehicle":
                boost += 0.6
            if analyzed.wants_status and h.entity_type == "document" and not analyzed.wants_policy:
                boost -= 1.5
            if analyzed.wants_policy and h.entity_type == "document":
                boost += 1.0
            # Lexical token overlap
            for tok in re.findall(r"[a-zA-Z\u0600-\u06FF]{3,}", q):
                if tok in blob:
                    boost += 0.15
            if len(set(h.sources) - {"sql"}) >= 1 and "sql" in h.sources:
                boost += 0.2
            if "vector" in h.sources and ("text" in h.sources or "exact" in h.sources):
                boost += 0.3
            h.score += boost
        hits.sort(key=lambda x: x.score, reverse=True)
        return hits

    def _build_context(self, hits: list[FusedHit], *, limit: int) -> str:
        parts: list[str] = []
        used = 0
        for i, h in enumerate(hits, start=1):
            block = (
                f"[{i}] ({h.entity_type}) {h.title}\n"
                f"{h.content}\n"
                f"sources={','.join(h.sources)} score={h.score:.4f}\n"
            )
            if used + len(block) > limit:
                break
            parts.append(block)
            used += len(block)
        return "\n".join(parts)

    async def _answer(
        self, analyzed: AnalyzedQuery, hits: list[FusedHit], context: str
    ) -> tuple[str, str]:
        extractive = self._extractive_answer(analyzed, hits, context)
        if not hits:
            return extractive, "extractive"

        try:
            from app.ai.llm import get_llm_client

            client = get_llm_client()
            if client is None:
                return extractive, "extractive"
            system = (
                "You are an operations assistant for an auto dealership. "
                "Answer ONLY using the provided CONTEXT. "
                "If context lacks the answer, say you could not find it. "
                "Never invent vehicles, people, prices, or policies. "
                "Reply in the same language as the user question (Persian or English). "
                "Be concise: 2–6 short sentences. Mention status/stock when present. "
                "For availability questions (موجود / do we have), clearly say yes/no and status."
            )
            user = (
                f"QUESTION:\n{analyzed.raw}\n\nCONTEXT:\n{context}\n\n"
                "Write the grounded answer now (plain text, no JSON)."
            )
            text = await client.chat_text(system=system, user=user, temperature=0.2)
            text = (text or "").strip()
            if not text:
                return extractive, "extractive"
            cites = self._cite_lines(hits)
            return f"{text}\n\nمنابع:\n" + "\n".join(cites), "llm"
        except Exception as exc:  # noqa: BLE001
            log.warning("llm_answer_failed", error=str(exc))
            return (
                extractive
                + f"\n\n_(LLM در دسترس نبود: {exc}. پاسخ استخراجی از موجودی/جستجو.)_",
                "extractive",
            )

    def _cite_lines(self, hits: list[FusedHit]) -> list[str]:
        lines = []
        for i, h in enumerate(hits[:4], start=1):
            label = {
                "vehicle": "خودرو",
                "work_item": "کار",
                "case": "پیگیری",
                "user": "فرد",
                "document": "قانون/دانش",
            }.get(h.entity_type, h.entity_type)
            lines.append(f"[{i}] {label}: {h.title}")
        return lines

    def _extractive_answer(
        self, analyzed: AnalyzedQuery, hits: list[FusedHit], context: str
    ) -> str:
        """Fallback when LLM is off — still grounded, no invented entities."""
        if not hits:
            return (
                "چیزی در محدودهٔ دسترسی شما پیدا نشد. "
                "شماره انبار، VIN، برند/مدل، یا قانون را دقیق‌تر بپرسید."
            )

        top = hits[0]
        cites = self._cite_lines(hits)

        if top.entity_type == "vehicle" or analyzed.brand or analyzed.model or analyzed.wants_status:
            status = str(top.metadata.get("status") or "")
            stock = top.metadata.get("stock_number") or ""
            year = top.metadata.get("year") or ""
            avail = "بله، موجود است" if status == "IN_STOCK" else (
                "رزرو شده است" if status == "RESERVED" else f"وضعیت فعلی: {status or 'نامشخص'}"
            )
            if analyzed.wants_status or "موجود" in analyzed.raw:
                head = f"{avail} — «{top.title}»"
            else:
                head = f"خودرو «{top.title}»"
            bits = [b for b in (f"وضعیت {status}" if status else "", f"#{stock}" if stock else "", str(year) if year else "") if b]
            if bits:
                head = f"{head} ({' · '.join(bits)})"
            body = top.content.strip()
            return f"{head}\n{body}\n\nمنابع:\n" + "\n".join(cites)

        if analyzed.vin or analyzed.stock_number or analyzed.case_number:
            return (
                f"پیدا شد — {top.entity_type} «{top.title}».\n"
                f"{top.content.strip()}\n\n"
                f"منابع:\n" + "\n".join(cites)
            )

        snippet = top.content.strip()
        if len(snippet) > 500:
            snippet = snippet[:500].rstrip() + "…"
        return "\n".join(
            [
                snippet,
                "",
                f"بر اساس {len(hits)} منبع بازیابی‌شده:",
                *cites,
            ]
        )
