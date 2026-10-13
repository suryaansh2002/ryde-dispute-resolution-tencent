"""Assemble prototype/index.html: the app template plus the data snapshot inlined.

The snapshot (data.json) is real pipeline output pulled from the Neon DB on 2026-10-13
(cases, decisions, evidence, trace events, token usage, the review queue and the golden
run). Heavy fields the prototype never reads are dropped here to keep the page small.

Run from the repo root: python3 prototype/build.py
"""

import json
from pathlib import Path

HERE = Path(__file__).parent
data = json.loads((HERE / "data.json").read_text())

for case in data["cases"].values():
    for event in case["trace"]:
        if event["agent"] == "evidence_collection" and event["kind"] == "agent_output" and event["output"]:
            out = event["output"]
            event["output"] = {
                "counts": {
                    "chat": len(out.get("chat_log") or []),
                    "gps": len(out.get("gps_trace") or []),
                    "photos": len(out.get("photos") or []),
                    "traffic": len(out.get("traffic_events") or []),
                },
                "policy_tags": [t.get("chunk_id") for t in out.get("policy_tags") or []],
            }

payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
template = (HERE / "src" / "app.html").read_text()
(HERE / "index.html").write_text(template.replace("__DATA__", payload))
print(f"wrote prototype/index.html ({len(payload) // 1024} KB data)")
