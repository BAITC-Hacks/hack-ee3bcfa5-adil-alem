"""Manual, opt-in real API verification. Never imported by regression tests.

Uses an isolated local database and records sanitized synthetic scenario evidence.
Run --help; each command performs one interview action, not an entire paid suite.
"""

import argparse
import json
import logging
import os
from pathlib import Path
import re

from dotenv import dotenv_values


GOLDEN_DRAFT = (
    "Our employees spend too much time reviewing contracts.\n"
    "We want to automate this process."
)
ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / ".openai-verification"
TRACE = ARTIFACTS / "trace.json"
MAX_CALLS = 8


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=[
        "start", "answer", "dont_know", "dont_understand", "needs_expert", "retry", "inspect",
    ])
    parser.add_argument("--allow-real-api", action="store_true")
    parser.add_argument("--field")
    parser.add_argument("--answer")
    parser.add_argument("--expert")
    args = parser.parse_args()
    if args.action != "inspect" and not args.allow_real_api:
        parser.error("Use --allow-real-api to explicitly authorize paid API calls.")

    config = dotenv_values(ROOT / ".env")
    secret = (config.get("OPENAI_API_KEY") or "").strip()
    model = (config.get("OPENAI_MODEL") or "").strip()
    if args.action != "inspect" and (not secret or model != "gpt-5.4-mini"):
        parser.error("A local API key and exact OPENAI_MODEL=gpt-5.4-mini are required.")
    os.environ["OPENAI_API_KEY"] = secret
    os.environ["OPENAI_MODEL"] = model
    os.environ.pop("OPENAI_LOG", None)
    logging.disable(logging.CRITICAL)
    ARTIFACTS.mkdir(exist_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite:///{(ARTIFACTS / 'session.db').as_posix()}"
    trace = json.loads(TRACE.read_text(encoding="utf-8")) if TRACE.exists() else {
        "golden_draft": GOLDEN_DRAFT, "calls": [], "steps": [],
    }

    def sanitize(value):
        encoded = json.dumps(value, ensure_ascii=False, default=str)
        if secret:
            encoded = encoded.replace(secret, "[REDACTED]")
        encoded = re.sub(r"sk-[A-Za-z0-9_-]+", "[REDACTED]", encoded)
        return json.loads(encoded)

    def save():
        TRACE.write_text(json.dumps(sanitize(trace), indent=2, ensure_ascii=False), encoding="utf-8")

    from openai import OpenAI
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import ai_interviewer

    class AuditedOpenAI(OpenAI):
        """Observes real SDK calls; never substitutes a model response."""

        def __enter__(self):
            client = super().__enter__()
            if client.base_url.scheme != "https" or client.base_url.host != "api.openai.com":
                client.close()
                raise RuntimeError("Manual verification requires the official OpenAI API endpoint")
            actual_parse = client.responses.parse

            def observed_parse(**kwargs):
                if len(trace["calls"]) >= MAX_CALLS:
                    raise RuntimeError("Manual verification call budget exhausted")
                if kwargs["model"] != "gpt-5.4-mini":
                    raise RuntimeError("Unexpected model; no fallback permitted")
                record = {
                    "number": len(trace["calls"]) + 1,
                    "request_model": kwargs["model"],
                    "api_host": client.base_url.host,
                    "request": json.loads(kwargs["input"][1]["content"]),
                    "store": kwargs["store"],
                    "max_retries": self.max_retries,
                }
                trace["calls"].append(record)
                save()
                try:
                    result = actual_parse(**kwargs)
                    record.update({
                        "response_model": result.model,
                        "response_id": result.id,
                        "status": result.status,
                        "usage": result.usage.model_dump() if result.usage else None,
                        "output": result.output_parsed.model_dump() if result.output_parsed else None,
                        "output_text": result.output_text,
                    })
                    return result
                except Exception as exc:
                    record["error"] = {"type": type(exc).__name__, "http_status": getattr(exc, "status_code", None)}
                    body = getattr(exc, "body", None)
                    if isinstance(body, dict):
                        error = body.get("error", body)
                        if isinstance(error, dict):
                            record["error"]["provider"] = {
                                key: error[key] for key in ("message", "type", "code", "param") if key in error
                            }
                    raise
                finally:
                    save()

            client.responses.parse = observed_parse
            return client

    ai_interviewer.OpenAI = AuditedOpenAI
    previous_calls = len(trace["calls"])
    with TestClient(app, raise_server_exceptions=False) as client:
        if args.action == "start":
            if "task_id" in trace:
                parser.error("Scenario already exists; inspect or retry it without creating another.")
            task_response = client.post("/api/tasks", json={"context": GOLDEN_DRAFT})
            task_response.raise_for_status()
            trace["task_id"] = task_response.json()["id"]
            save()
        if "task_id" not in trace:
            parser.error("Start the isolated scenario first.")
        base = f"/api/tasks/{trace['task_id']}"
        state = client.get(base + "/interview").json()
        if args.action in ("start", "retry"):
            response = client.post(base + "/interview/" + args.action)
        elif args.action == "inspect":
            response = client.get(base + "/interview")
        else:
            question = next((q for q in state["questions"] if q["field"] == args.field), None)
            if question is None:
                parser.error("--field must match an existing pending question.")
            payload = {"question_id": question["id"], "action": args.action}
            if args.answer is not None:
                payload["answer"] = args.answer
            if args.expert is not None:
                payload["expert"] = args.expert
            response = client.post(base + "/interview/respond", json=payload)
        step = {
            "action": args.action, "http_status": response.status_code,
            "state": response.json(), "task": client.get(base).json(),
        }
        if args.action != "inspect":
            trace["steps"].append(step)
            save()
        print(json.dumps(sanitize({
            "total_attempts": len(trace["calls"]),
            "new_calls": [
                {key: value for key, value in call.items() if key not in ("request", "output_text")}
                for call in trace["calls"][previous_calls:]
            ], "step": step,
        }), indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
