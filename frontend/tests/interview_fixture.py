"""Explicit AI test double. Imported ONLY by the isolated browser test server."""

from app.services.ai_interviewer import InterviewAIError

QUESTIONS = {
    "need": "What would you like to change about the way this work happens?",
    "users": "Who is affected by this problem in your organization?",
    "data": "What information or materials does your organization currently use for this work?",
    "expected_result": "What result would help you with this problem?",
    "constraints": "What restrictions must a team take into account?",
    "success_criteria": "How would you recognize a useful result?",
    "contact": "Who can the student team contact about this challenge?",
    "interaction_format": "How would you like to work with the student team?",
    "context": "What happens in your organization when this problem occurs?",
}
_failed_sources = set()


def generate_interview(payload):
    # Deterministic outage once per draft, followed by successful explicit retry.
    for source in payload["sources"]:
        if "Demo outage" in source["text"] and source["id"] not in _failed_sources:
            _failed_sources.add(source["id"])
            raise InterviewAIError("AI is temporarily unavailable. Your information is saved. Please retry.")
    mode = payload["mode"]
    if mode in ("rephrase", "verification"):
        question = payload["question"]
        text = ("Who experiences this problem?" if mode == "rephrase"
                else "What makes this information not applicable to your challenge?")
        return {"extractions": [], "questions": [{"field": question["field"], "text": text, "difficulty": "QUICK"}], "can_finish": False}
    if mode == "extract":
        source = payload["sources"][-1]
        item = next(item for item in payload["items"] if item["source"] == source["id"])
        return {"extractions": [{"field": item["field"], "value": source["text"], "source": source["id"], "conflicting_with": None}], "questions": [], "can_finish": False}
    eligible = payload["eligible_fields"]
    fields = [field for field in QUESTIONS if field in eligible][:payload["question_count"]]
    return {"extractions": [], "questions": [{"field": field, "text": QUESTIONS[field], "difficulty": "QUICK" if index == 0 else "THINK"} for index, field in enumerate(fields)], "can_finish": not fields}
