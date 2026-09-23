"""Explicit, bounded real execution-test verification; never part of regression.

Copies the saved Step 7.5 golden database into an isolated local directory.
Actions inspect and confirm-known never call AI; run requires --allow-real-api.
"""

import argparse
import json
import logging
import os
from pathlib import Path
import re
import sqlite3

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / ".stress-verification"
MAX_ATTEMPTS = 4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run", "inspect", "confirm-known"])
    parser.add_argument("--allow-real-api", action="store_true")
    args = parser.parse_args()
    if args.action == "run" and not args.allow_real_api:
        parser.error("Paid calls require --allow-real-api.")
    config = dotenv_values(ROOT / ".env")
    secret = (config.get("OPENAI_API_KEY") or "").strip()
    model = (config.get("OPENAI_MODEL") or "").strip()
    if args.action == "run" and (not secret or model != "gpt-5.4-mini"):
        parser.error("Local API key and exact OPENAI_MODEL=gpt-5.4-mini required.")
    os.environ["OPENAI_API_KEY"] = secret
    os.environ["OPENAI_MODEL"] = model
    os.environ.pop("OPENAI_LOG", None)
    logging.disable(logging.CRITICAL)

    ARTIFACTS.mkdir(exist_ok=True)
    db_path = ARTIFACTS / "session.db"
    trace_path = ARTIFACTS / "trace.json"
    previous_trace = ROOT / ".openai-verification" / "trace.json"
    previous_db = previous_trace.with_name("session.db")
    if not db_path.exists():
        if not previous_trace.exists() or not previous_db.exists():
            parser.error("The saved Step 7.5 golden scenario is required. No substitute data was created.")
        with sqlite3.connect(previous_db.as_uri() + "?mode=ro", uri=True) as source:
            with sqlite3.connect(db_path) as destination:
                source.backup(destination)
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    trace = json.loads(trace_path.read_text(encoding="utf-8")) if trace_path.exists() else {
        "task_id": json.loads(previous_trace.read_text(encoding="utf-8"))["task_id"],
        "calls": [], "steps": [],
    }

    def safe(value):
        encoded = json.dumps(value, ensure_ascii=False, default=str)
        if secret:
            encoded = encoded.replace(secret, "[REDACTED]")
        return json.loads(re.sub(r"sk-[A-Za-z0-9_-]+", "[REDACTED]", encoded))

    def save():
        trace_path.write_text(json.dumps(safe(trace), indent=2, ensure_ascii=False), encoding="utf-8")

    from fastapi.testclient import TestClient
    from openai import OpenAI
    from app.main import app
    from app.services import ai_interviewer

    class ObservedOpenAI(OpenAI):
        def __enter__(self):
            client = super().__enter__()
            if client.base_url.scheme != "https" or client.base_url.host != "api.openai.com":
                client.close()
                raise RuntimeError("Official OpenAI API endpoint required")
            original = client.responses.parse

            def parse(**kwargs):
                if args.action != "run" or len(trace["calls"]) >= MAX_ATTEMPTS:
                    raise RuntimeError("No paid calls authorized or call budget exhausted")
                if kwargs["model"] != "gpt-5.4-mini":
                    raise RuntimeError("Unexpected model; no fallback permitted")
                call = {
                    "number": len(trace["calls"]) + 1, "request_model": kwargs["model"],
                    "api_host": client.base_url.host, "max_retries": self.max_retries,
                    "store": kwargs["store"],
                    "request": json.loads(kwargs["input"][1]["content"]),
                }
                trace["calls"].append(call)
                save()
                try:
                    response = original(**kwargs)
                    call.update({
                        "response_model": response.model, "response_id": response.id,
                        "status": response.status,
                        "usage": response.usage.model_dump() if response.usage else None,
                        "output": response.output_parsed.model_dump() if response.output_parsed else None,
                        "output_text": response.output_text,
                    })
                    return response
                except Exception as exc:
                    call["error"] = {"type": type(exc).__name__, "http_status": getattr(exc, "status_code", None)}
                    body = getattr(exc, "body", None)
                    if isinstance(body, dict):
                        error = body.get("error", body)
                        if isinstance(error, dict):
                            call["error"]["provider"] = {k: error[k] for k in ("message", "type", "code", "param") if k in error}
                    raise
                finally:
                    save()

            client.responses.parse = parse
            return client

    ai_interviewer.OpenAI = ObservedOpenAI
    before_calls = len(trace["calls"])
    with TestClient(app, raise_server_exceptions=False) as client:
        base = f"/api/tasks/{trace['task_id']}"
        before = client.get(base).json()
        if args.action == "confirm-known":
            knowledge = client.get(base + "/interview").json()
            values = {item["field"]: item["value"] for item in knowledge["items"] if item["field"] in ("context", "need")}
            assert all(values.values()), "Original context and answer must both exist"
            client.patch(base, json=values).raise_for_status()
            client.post(base + "/confirm", json={"fields": list(values)}).raise_for_status()
        response = client.post(base + "/stress-test") if args.action == "run" else client.get(base + "/stress-test")
        response.raise_for_status()
        after = client.get(base).json()
        if args.action == "run":
            assert before == after, "Stress test unexpectedly changed the Task"
        step = {"action": args.action, "task_before": before, "task_after": after, "response": response.json()}
        if args.action != "inspect":
            trace["steps"].append(step)
            save()
        print(json.dumps(safe({
            "attempts": len(trace["calls"]),
            "new_calls": [{k: v for k, v in c.items() if k not in ("request", "output_text")} for c in trace["calls"][before_calls:]],
            "step": step,
        }), indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
