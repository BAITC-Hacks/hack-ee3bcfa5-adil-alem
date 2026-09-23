"""Deterministic scoring of plain task mappings; no I/O or mutation."""

import re
from collections.abc import Mapping, Iterable


CATEGORIES = {
    "context_need": {"context": 10, "need": 10},
    "data": {"data": 20},
    "expected_result": {"expected_result": 15},
    "success_criteria": {"success_criteria": 15},
    "constraints": {"constraints": 10},
    "users": {"users": 10},
    "business_connection": {"contact": 5, "interaction_format": 5},
}
CONFIRMABLE_FIELDS = tuple(field for fields in CATEGORIES.values() for field in fields)
PLACEHOLDERS = {"yes", "no", "none", "test", "na", "tbd", "todo", "unknown", "null"}


def normalized_text(value: object) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def is_meaningful(value: object, field: str) -> bool:
    text = normalized_text(value)
    words = re.findall(r"[^\W_]+", text.casefold())
    compact = "".join(words)
    minimum = 5 if field == "contact" else 10
    return (
        len(text) >= minimum
        and bool(words)
        and compact not in PLACEHOLDERS
        and not all(word in PLACEHOLDERS for word in words)
        and len(set(compact)) >= 3
    )


def readiness_level(score: int) -> str:
    if not 0 <= score <= 100:
        raise ValueError("Score must be between 0 and 100")
    return "priority" if score >= 90 else "ready" if score >= 70 else "working" if score >= 40 else "draft"


def calculate_score(task: Mapping[str, object], confirmed_fields: Iterable[str] = ()) -> dict:
    confirmed = set(confirmed_fields)
    breakdown = {}
    missing_fields = []
    recommendations = []
    for category, fields in CATEGORIES.items():
        points = 0
        missing = []
        reasons = []
        for field, maximum in fields.items():
            text = normalized_text(task.get(field))
            meaningful = is_meaningful(text, field)
            if not meaningful:
                earned = 0
                action = "Add meaningful information and confirm it."
            elif field not in confirmed:
                earned = 0
                action = "Confirm this information with the business."
            elif field == "contact":
                earned = maximum
                action = "Confirmed contact is present."
            elif len(text) < 30:
                earned = maximum // 2
                action = "Expand to at least 30 normalized characters and reconfirm."
            elif field == "success_criteria" and not re.search(r"\d", text):
                earned = maximum // 2
                action = "Add a numeric target and reconfirm."
            else:
                earned = maximum
                action = "Confirmed information meets the documented checks."
            points += earned
            reasons.append(f"{field}: {earned}/{maximum}. {action}")
            if earned < maximum:
                missing.append(field)
                missing_fields.append(field)
                recommendations.append({
                    "field": field, "potential_gain": maximum - earned, "message": action,
                })
        breakdown[category] = {
            "score": points, "max": sum(fields.values()),
            "missing": missing, "reason": " ".join(reasons),
        }
    total = sum(category["score"] for category in breakdown.values())
    next_threshold, next_level = next(
        ((threshold, level) for threshold, level in ((40, "working"), (70, "ready"), (90, "priority"))
        if total < threshold
    ), (total, None))
    return {
        "score": total, "level": readiness_level(total), "breakdown": breakdown,
        "missing_fields": missing_fields, "recommendations": recommendations,
        "points_to_next_level": next_threshold - total, "next_level": next_level,
    }
