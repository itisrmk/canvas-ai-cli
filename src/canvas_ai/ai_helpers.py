from __future__ import annotations

import os


def llm_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))


def generate_draft(assignment: dict) -> str:
    title = assignment.get("name", "Untitled Assignment")
    if not llm_available():
        return (
            f"[Placeholder draft for: {title}]\n"
            "No LLM API key found. Add OPENAI_API_KEY or ANTHROPIC_API_KEY to enable AI drafting.\n"
            "Suggested approach:\n"
            "1. Restate the prompt in your own words.\n"
            "2. Outline key points and required evidence.\n"
            "3. Write your own first draft and review for originality."
        )
    return f"AI draft generation is configured but not implemented in v1 for '{title}'."


def generate_plan(assignment: dict) -> list[str]:
    title = assignment.get("name", "Untitled Assignment")
    return [
        f"Understand requirements for '{title}'",
        "Break prompt into subtasks and acceptance criteria",
        "Collect references/materials",
        "Draft response in your own words",
        "Revise for clarity and citation compliance",
        "Final human review before submission",
    ]
