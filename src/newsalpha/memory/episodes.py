"""Episode memory store — Qdrant-backed (with in-memory fallback for tests).

Schema: each episode = one closed trade's reflection. Fields:
  - ticker, side, entry_date, exit_date
  - pnl_pct, conviction
  - regime (macro context label)
  - what_worked, what_failed, lessons (LLM-generated)
  - key_signals (which analyst signals carried weight)

Embeddings: produced from a compact text summary (ticker + event_type +
regime + lessons) so retrieval finds *structurally similar* past trades
during future debates.

Embedding strategy: use Anthropic's text-only embeddings is not yet available
in the SDK we're using; we use a deterministic hash-based embedding for
testing and a real embedding model when configured. This keeps the W4 work
testable without external dependencies.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from newsalpha.utils.logging import get_logger

log = get_logger(__name__)

EMBEDDING_DIM = 256
COLLECTION_NAME = "episodes"


@dataclass
class Episode:
    """One closed trade's reflection record."""

    ticker: str
    side: str
    entry_date: str
    exit_date: str
    pnl_pct: float
    conviction: float
    regime: str = "unknown"
    what_worked: list[str] = field(default_factory=list)
    what_failed: list[str] = field(default_factory=list)
    lessons: list[str] = field(default_factory=list)
    key_signals: list[str] = field(default_factory=list)
    trace_id: str = ""
    created_at: str = ""

    def to_text_summary(self) -> str:
        """Compact text representation for embedding."""
        parts = [
            f"ticker={self.ticker}",
            f"side={self.side}",
            f"regime={self.regime}",
            f"pnl={self.pnl_pct:.3f}",
            f"conviction={self.conviction:.2f}",
        ]
        if self.lessons:
            parts.append("lessons: " + "; ".join(self.lessons[:3]))
        if self.key_signals:
            parts.append("signals: " + ", ".join(self.key_signals[:5]))
        return " | ".join(parts)

    def to_payload(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "side": self.side,
            "entry_date": self.entry_date,
            "exit_date": self.exit_date,
            "pnl_pct": self.pnl_pct,
            "conviction": self.conviction,
            "regime": self.regime,
            "what_worked": self.what_worked,
            "what_failed": self.what_failed,
            "lessons": self.lessons,
            "key_signals": self.key_signals,
            "trace_id": self.trace_id,
            "created_at": self.created_at,
            "text_summary": self.to_text_summary(),
        }

    @classmethod
    def from_payload(cls, p: dict[str, Any]) -> Episode:
        return cls(
            ticker=p.get("ticker", ""),
            side=p.get("side", ""),
            entry_date=p.get("entry_date", ""),
            exit_date=p.get("exit_date", ""),
            pnl_pct=float(p.get("pnl_pct", 0.0)),
            conviction=float(p.get("conviction", 0.0)),
            regime=p.get("regime", "unknown"),
            what_worked=list(p.get("what_worked", [])),
            what_failed=list(p.get("what_failed", [])),
            lessons=list(p.get("lessons", [])),
            key_signals=list(p.get("key_signals", [])),
            trace_id=p.get("trace_id", ""),
            created_at=p.get("created_at", ""),
        )


def embed_text(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Deterministic hash-based embedding.

    Maps text → fixed-dim float vector via SHA-256 byte chunks. This is NOT a
    semantic embedding — it's a placeholder that gives consistent vectors for
    identical texts so the storage/retrieval plumbing can be tested end-to-end
    without an embedding API.

    In production, swap this for `voyage-3` or `text-embedding-3-large` etc.
    """
    h = hashlib.sha256(text.encode("utf-8")).digest()
    repeats = (dim * 4 + len(h) - 1) // len(h)
    expanded = (h * repeats)[: dim * 4]
    out: list[float] = []
    for i in range(dim):
        byte_chunk = expanded[i * 4 : (i + 1) * 4]
        val = int.from_bytes(byte_chunk, "big", signed=False)
        out.append((val / 0xFFFFFFFF) * 2.0 - 1.0)
    # Normalize to unit length for cosine similarity.
    norm = sum(x * x for x in out) ** 0.5
    if norm == 0:
        return out
    return [x / norm for x in out]


class InMemoryEpisodeStore:
    """Dict-backed store. Used when Qdrant is unreachable or in unit tests."""

    def __init__(self) -> None:
        self._items: list[tuple[str, list[float], dict[str, Any]]] = []

    def upsert(self, episode_id: str, vector: list[float], payload: dict[str, Any]) -> None:
        self._items = [(eid, v, p) for eid, v, p in self._items if eid != episode_id]
        self._items.append((episode_id, vector, payload))

    def search(
        self,
        query_vector: list[float],
        limit: int = 3,
        ticker_filter: str | None = None,
    ) -> list[tuple[float, dict[str, Any]]]:
        """Cosine similarity search. Returns [(score, payload), ...]."""
        results: list[tuple[float, dict[str, Any]]] = []
        for _, v, p in self._items:
            if ticker_filter and p.get("ticker") != ticker_filter:
                continue
            score = _cosine_similarity(query_vector, v)
            results.append((score, p))
        results.sort(key=lambda x: x[0], reverse=True)
        return results[:limit]

    def count(self) -> int:
        return len(self._items)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class QdrantEpisodeStore:
    """Qdrant-backed store. Falls back to in-memory if connection fails."""

    def __init__(self, url: str | None = None) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.http.models import Distance, VectorParams

        if url is None:
            from newsalpha.core.config import get_settings
            url = get_settings().qdrant_url

        self._client = QdrantClient(url=url)
        try:
            self._client.get_collection(COLLECTION_NAME)
        except Exception:  # noqa: BLE001
            self._client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
            )

    def upsert(self, episode_id: str, vector: list[float], payload: dict[str, Any]) -> None:
        from qdrant_client.http.models import PointStruct

        self._client.upsert(
            collection_name=COLLECTION_NAME,
            points=[PointStruct(id=episode_id, vector=vector, payload=payload)],
        )

    def search(
        self,
        query_vector: list[float],
        limit: int = 3,
        ticker_filter: str | None = None,
    ) -> list[tuple[float, dict[str, Any]]]:
        from qdrant_client.http.models import FieldCondition, Filter, MatchValue

        flt = None
        if ticker_filter:
            flt = Filter(must=[
                FieldCondition(key="ticker", match=MatchValue(value=ticker_filter))
            ])

        hits = self._client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=limit,
            query_filter=flt,
        )
        return [(float(h.score), dict(h.payload or {})) for h in hits]

    def count(self) -> int:
        info = self._client.get_collection(COLLECTION_NAME)
        return int(info.points_count or 0)


def get_default_store() -> InMemoryEpisodeStore | QdrantEpisodeStore:
    """Try Qdrant; fall back to in-memory if unreachable.

    Env override: `NEWSALPHA_MEMORY_BACKEND=memory` forces in-memory.
    """
    import os

    if os.environ.get("NEWSALPHA_MEMORY_BACKEND") == "memory":
        return InMemoryEpisodeStore()

    try:
        return QdrantEpisodeStore()
    except Exception as exc:  # noqa: BLE001
        log.warning("qdrant_unavailable_using_memory", error=str(exc))
        return InMemoryEpisodeStore()


def write_episode(
    episode: Episode,
    store: InMemoryEpisodeStore | QdrantEpisodeStore | None = None,
) -> str:
    """Write an episode to the store. Returns the episode_id used."""
    s = store or get_default_store()
    if not episode.created_at:
        episode.created_at = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    episode_id = _make_episode_id(episode)
    vector = embed_text(episode.to_text_summary())
    s.upsert(episode_id, vector, episode.to_payload())

    log.info(
        "episode_written",
        episode_id=episode_id,
        ticker=episode.ticker,
        pnl_pct=round(episode.pnl_pct, 4),
        regime=episode.regime,
    )
    return episode_id


def retrieve_similar(
    query_text: str,
    *,
    ticker: str | None = None,
    limit: int = 3,
    store: InMemoryEpisodeStore | QdrantEpisodeStore | None = None,
) -> list[Episode]:
    """Retrieve top-K most similar past episodes."""
    s = store or get_default_store()
    qv = embed_text(query_text)
    hits = s.search(qv, limit=limit, ticker_filter=ticker)
    return [Episode.from_payload(payload) for _, payload in hits]


def _make_episode_id(ep: Episode) -> str:
    raw = f"{ep.ticker}|{ep.entry_date}|{ep.exit_date}|{ep.trace_id}|{ep.created_at}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()
