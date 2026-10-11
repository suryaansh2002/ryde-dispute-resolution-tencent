"""Policy RAG (system design §6): search over the `policy_chunks` corpus.

BM25 keyword ranking over the ingested corpus for now. The pgvector path needs an
embedding provider (Groq doesn't serve embeddings) — swap the ranking in
`search_policy` once that's chosen; callers only see `PolicyTag` hits.
"""

import json
import math
import re
from collections import Counter
from functools import cache
from pathlib import Path

from app.schemas import PolicyTag

CORPUS = Path(__file__).resolve().parents[2] / "data_generation" / "fixtures" / "policy_chunks.json"

_TOKEN = re.compile(r"[a-z0-9]+")
_K1, _B = 1.5, 0.75


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@cache
def _index() -> tuple[list[PolicyTag], list[Counter], Counter, float]:
    tags, docs = [], []
    for c in json.loads(CORPUS.read_text()):
        tags.append(PolicyTag(chunk_id=c["chunk_id"], policy_id=c["policy_id"],
                              excerpt=f"§{c['heading']} — {c['text']}"))
        docs.append(Counter(_tokens(f"{c['heading']} {c['text']}")))
    df = Counter(t for d in docs for t in d)
    avg_len = sum(sum(d.values()) for d in docs) / len(docs)
    return tags, docs, df, avg_len


def search_policy(query: str, k: int = 3) -> list[PolicyTag]:
    tags, docs, df, avg_len = _index()
    n = len(docs)
    terms = set(_tokens(query))
    scored = []
    for tag, doc in zip(tags, docs, strict=True):
        length = sum(doc.values())
        score = sum(
            math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            * doc[t] * (_K1 + 1) / (doc[t] + _K1 * (1 - _B + _B * length / avg_len))
            for t in terms if t in doc
        )
        if score > 0:
            scored.append((score, tag))
    scored.sort(key=lambda st: st[0], reverse=True)
    return [tag for _, tag in scored[:k]]


def policy_clauses(policy_id: str) -> list[PolicyTag]:
    """Every chunk of one policy section, in document order: what a cited POL-0N says."""
    tags, *_ = _index()
    return [t for t in tags if t.policy_id == policy_id]
