"""Chunk Policy doc Part 1 into `policy_chunks`-shaped records.

Writes `data_generation/fixtures/policy_chunks.json`. Policy IDs follow the doc's own
section numbers (§2 Route Deviation -> POL-02, ...). Text is kept verbatim, including
the inline "not Ryde-sourced" caveats, so retrieved chunks carry their own provenance.

Run from backend/: `uv run python -m data_generation.pipeline.ingest_policy`
"""

import json
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
POLICY_DOC = BACKEND.parent / "docs" / "RydeResolve-Policy-and-Prevention-Rules.md"
OUT = BACKEND / "data_generation" / "fixtures" / "policy_chunks.json"

MIN_CHUNK_CHARS = 250
SECTION_RE = re.compile(r"^### (\d+)\. (.+)$")


def _paragraphs(lines: list[str]) -> list[str]:
    paras, buf = [], []
    for line in lines:
        if line.strip() and line.strip() != "---":
            buf.append(line.rstrip())
        elif buf:
            paras.append("\n".join(buf))
            buf = []
    if buf:
        paras.append("\n".join(buf))
    # Short lead-ins ("Four principles apply...:") read better merged with what follows.
    merged: list[str] = []
    for p in paras:
        if merged and len(merged[-1]) < MIN_CHUNK_CHARS:
            merged[-1] = f"{merged[-1]}\n\n{p}"
        else:
            merged.append(p)
    return merged


def chunk_policy(doc: str) -> list[dict]:
    part1 = doc.split("## Part 1", 1)[1].split("## Part 2", 1)[0]
    sections: list[tuple[int, str, list[str]]] = []
    for line in part1.splitlines():
        m = SECTION_RE.match(line)
        if m:
            sections.append((int(m.group(1)), m.group(2).strip(), []))
        elif sections:
            sections[-1][2].append(line)

    chunks = []
    for num, title, lines in sections:
        policy_id = f"POL-{num:02d}"
        for i, text in enumerate(_paragraphs(lines), start=1):
            chunks.append({
                "chunk_id": f"{policy_id}-{i:02d}",
                "policy_id": policy_id,
                "heading": f"{num}. {title}",
                "text": text,
                "source": POLICY_DOC.name,
            })
    return chunks


def main() -> None:
    chunks = chunk_policy(POLICY_DOC.read_text())
    OUT.write_text(json.dumps(chunks, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(chunks)} chunks to {OUT.relative_to(BACKEND)}")


if __name__ == "__main__":
    main()
