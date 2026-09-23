"""Provider-only test double for execution browser tests. Never calls OpenAI."""

from app.services.ai_interviewer import InterviewAIError

_calls = {}


def generate_stress_test(payload):
    title = payload["task"].get("title") or ""
    _calls[title] = _calls.get(title, 0) + 1
    if "Execution outage" in title and _calls[title] == 2:
        raise InterviewAIError("The execution test is temporarily unavailable. Your previous result is saved. Please retry.")

    items = {item["field"]: item for item in payload["items"]}
    sources = {source["id"]: source for source in payload["sources"]}
    basis = [ref for ref in ("task:context", "task:need") if sources.get(ref, {}).get("text")]
    scope = sources.get("task:need", {}).get("text") or ""
    design_only = "no existing dataset is required" in scope.lower()
    definitions = [
        ("UNDERSTAND", "context", "Business problem", "What business problem is the student team addressing?"),
        ("START", "need", "Scope of the work", "What part of the work should the student team begin with?"),
        ("ACCESS", "data", "Existing dataset" if design_only else "Access to contract materials", "What information or materials are available to the selected team?"),
        ("VALIDATE", "success_criteria", "Evaluation criteria", "How will the business evaluate the result?"),
        ("DELIVER", "expected_result", "Expected deliverable", "What should the team deliver?"),
    ]
    requirements = []
    for gate, field, requirement, information in definitions:
        item = items[field]
        evidence = []
        assessment = "MISSING"
        if item["status"] == "CONFIRMED" and item["confirmed"] and item["value"]:
            assessment = "SUPPORTED"
            evidence = [{"source_ref": f"task:{field}", "quote": item["value"]}]
        if field == "data" and design_only:
            assessment = "NOT_APPLICABLE"
            evidence = [{"source_ref": "task:need", "quote": scope}]
        requirements.append({
            "gate": gate, "field": field, "requirement": requirement,
            "required_information": information, "basis_refs": basis,
            "evidence": evidence, "assessment": assessment,
        })
    return {"requirements": requirements}
