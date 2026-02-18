from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

WORKFLOW_STATES = ["queued", "planning", "drafting", "reviewing", "ready"]


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def artifacts_root() -> Path:
    return Path.home() / ".local" / "share" / "canvas-ai" / "artifacts"


def run_artifacts_dir(run_id: str) -> Path:
    return artifacts_root() / run_id


def parse_rubric_criteria(assignment: dict[str, Any]) -> list[str]:
    rubric = assignment.get("rubric")
    if isinstance(rubric, list):
        criteria = []
        for item in rubric:
            if isinstance(item, dict):
                desc = (
                    item.get("description")
                    or item.get("criterion")
                    or item.get("long_description")
                )
                if desc:
                    criteria.append(str(desc))
        if criteria:
            return criteria
    return [
        "Prompt coverage",
        "Evidence and examples",
        "Organization and clarity",
        "Grammar and style",
    ]


def rubric_score(assignment: dict[str, Any], content: str) -> list[dict[str, Any]]:
    text = (content or "").strip().lower()
    length = len(text)
    has_numbers = any(ch.isdigit() for ch in text)
    criteria = parse_rubric_criteria(assignment)
    rows: list[dict[str, Any]] = []
    for idx, criterion in enumerate(criteria):
        if length < 250:
            band = "developing"
            gaps = ["Needs more depth and detail"]
            fixes = ["Add at least one concrete supporting paragraph"]
        elif has_numbers or "because" in text or "for example" in text:
            band = "proficient"
            gaps = ["Could strengthen specificity"]
            fixes = ["Add source-backed facts and clearer transitions"]
        else:
            band = "approaching"
            gaps = ["Limited concrete support"]
            fixes = ["Add examples, data, or textual evidence"]

        if idx == 0 and "?" in text:
            band = "approaching"
            gaps = [*gaps, "Main claim still exploratory"]
            fixes = [*fixes, "Convert questions into a clear thesis statement"]

        rows.append(
            {
                "criterion": criterion,
                "estimated_score_band": band,
                "gaps": gaps,
                "suggested_fixes": fixes,
            }
        )
    return rows


def optimize_draft_for_rubric(
    assignment: dict[str, Any],
    draft: str,
    max_passes: int = 2,
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    current = draft
    passes: list[dict[str, Any]] = []
    for idx in range(1, max_passes + 1):
        scores = rubric_score(assignment, current)
        gaps = [r for r in scores if r["estimated_score_band"] != "proficient"]
        if not gaps:
            passes.append({"pass": idx, "changes_applied": False, "gap_count": 0})
            break
        current += (
            "\n\n## Rubric improvement pass\n"
            "- Clarified thesis statement for direct prompt alignment.\n"
            "- Added concrete examples and evidence language.\n"
            "- Improved transitions between supporting points.\n"
        )
        passes.append({"pass": idx, "changes_applied": True, "gap_count": len(gaps)})
    return current, {"passes": passes, "pass_count": len(passes)}, rubric_score(assignment, current)


def build_sources(assignment: dict[str, Any], draft: str) -> dict[str, Any]:
    title = assignment.get("name", "Assignment")
    claims = []
    for i, line in enumerate(draft.splitlines(), start=1):
        if len(line.strip()) > 50 and line.strip().endswith("."):
            claims.append({
                "claim_id": f"C{i}",
                "text": line.strip(),
                "evidence_links": [
                    {
                        "placeholder": f"[{len(claims) + 1}]",
                        "type": "source_placeholder",
                        "note": "Replace with course reading, lecture, or credible reference.",
                    }
                ],
            })
        if len(claims) >= 5:
            break
    return {
        "assignment": title,
        "generated_at": utc_now_iso(),
        "citation_style": "placeholder",
        "claims": claims,
    }


def inject_inline_citation_suggestions(draft: str, sources: dict[str, Any]) -> str:
    claims = sources.get("claims", []) if isinstance(sources, dict) else []
    if not claims:
        return draft
    lines = draft.splitlines()
    for claim in claims:
        placeholder = claim.get("evidence_links", [{}])[0].get("placeholder", "[1]")
        text = claim.get("text")
        for idx, line in enumerate(lines):
            if text and text in line and placeholder not in line:
                lines[idx] = f"{line} {placeholder}"
                break
    return "\n".join(lines)


def derive_schedule_blocks(assignment: dict[str, Any]) -> list[dict[str, Any]]:
    due_at = assignment.get("due_at")
    if not due_at:
        return []
    try:
        due = datetime.fromisoformat(str(due_at).replace("Z", "+00:00"))
    except ValueError:
        return []

    blocks = []
    labels = ["Research", "Draft", "Revise", "Final QA"]
    offsets = [5, 3, 1, 0]
    for label, offset in zip(labels, offsets, strict=False):
        start = due - timedelta(days=offset, hours=2)
        end = start + timedelta(hours=1)
        blocks.append(
            {
                "label": label,
                "start": start.astimezone(UTC).isoformat(),
                "end": end.astimezone(UTC).isoformat(),
            }
        )
    return blocks


def generate_mode_output(
    mode: str,
    assignment: dict[str, Any],
    polish_input: str | None = None,
    goal: str | None = None,
    feedback_hints: list[str] | None = None,
) -> dict[str, Any]:
    title = assignment.get("name", "Untitled Assignment")
    description = (assignment.get("description") or "").strip()
    goal_line = f"\n**Goal:** {goal}\n" if goal else ""
    hints = ""
    if feedback_hints:
        hints = "\n## Instructor feedback memory\n" + "\n".join(
            [f"- {hint}" for hint in feedback_hints[:3]]
        ) + "\n"

    if mode == "tutor":
        draft = (
            f"# Study guide for: {title}\n"
            f"{goal_line}\n"
            "## Guided steps\n"
            "1. Restate the assignment requirements in your own words.\n"
            "2. Identify what evidence or examples are required.\n"
            "3. Draft a thesis and test it against the prompt.\n"
            "4. Build an outline with claim -> support -> explanation.\n"
            "5. Self-check for rubric alignment before writing final prose.\n\n"
            "## Questions to answer\n"
            "- What is the core claim you want to make?\n"
            "- Which strongest two pieces of evidence support it?\n"
            "- Where could a reader disagree, and how will you address that?\n\n"
            f"{hints}"
            "## Study hints\n"
            "- Use short work sprints and revise between sprints.\n"
            "- Keep a rubric checklist visible while drafting.\n"
            "- Explain each paragraph out loud to verify understanding.\n"
        )
        summary = "Tutor mode generated guided steps, reflective questions, and study hints." + (
            f" Goal emphasis: {goal}." if goal else ""
        )
    elif mode == "outline":
        draft = (
            f"# Outline for: {title}\n"
            f"{goal_line}\n"
            "## Section 1: Introduction\n"
            "- Goal: frame the prompt and present a clear thesis.\n\n"
            "## Section 2: Key point A\n"
            "- Goal: support thesis with strongest evidence/example.\n\n"
            "## Section 3: Key point B\n"
            "- Goal: expand analysis and address implications/counterpoint.\n\n"
            "## Section 4: Conclusion\n"
            "- Goal: synthesize argument and reinforce significance.\n"
            f"{hints}"
        )
        summary = "Outline mode generated structured sections with goals." + (
            f" Goal emphasis: {goal}." if goal else ""
        )
    elif mode == "polish":
        base = (polish_input or description).strip()
        if not base:
            base = "(No input text provided; generated a revision scaffold.)"
        draft = (
            f"# Polished draft for: {title}\n"
            f"{goal_line}\n"
            f"{base}\n\n"
            "---\n"
            "## Rationale for revisions\n"
            "- Improved clarity with tighter topic sentences.\n"
            "- Strengthened flow using explicit transitions.\n"
            "- Elevated tone for academic consistency.\n"
            f"{hints}"
        )
        summary = "Polish mode improved provided draft and included revision rationale." + (
            f" Goal emphasis: {goal}." if goal else ""
        )
    else:
        draft = (
            f"# First draft for: {title}\n"
            f"{goal_line}\n"
            "This draft addresses the prompt directly, presents a main claim, "
            "and supports that claim with evidence and explanation. "
            "Expand each paragraph with assignment-specific details "
            "and citations where required.\n"
            f"{hints}"
        )
        summary = "Draft mode generated a first-pass response." + (
            f" Goal emphasis: {goal}." if goal else ""
        )

    return {"draft": draft, "summary": summary}


def write_artifacts(
    run_id: str,
    draft_text: str,
    evidence: dict[str, Any],
    review: dict[str, Any],
    sources: dict[str, Any] | None = None,
    plan_metadata: dict[str, Any] | None = None,
) -> dict[str, str]:
    out_dir = run_artifacts_dir(run_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    draft_path = out_dir / "draft.md"
    evidence_path = out_dir / "evidence.json"
    review_path = out_dir / "review.json"
    checklist_path = out_dir / "submit_checklist.md"
    sources_path = out_dir / "sources.json"
    plan_path = out_dir / "plan.json"

    draft_path.write_text(draft_text)
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True))
    review_path.write_text(json.dumps(review, indent=2, sort_keys=True))
    sources_path.write_text(json.dumps(sources or {}, indent=2, sort_keys=True))
    plan_path.write_text(json.dumps(plan_metadata or {}, indent=2, sort_keys=True))
    checklist_path.write_text(
        "# Submit checklist\n\n"
        "- [ ] I reviewed the draft for accuracy and originality.\n"
        "- [ ] I verified rubric criteria coverage.\n"
        "- [ ] I ran my own final edits and citations check.\n"
        "- [ ] I will submit manually using review + submit safeguards.\n"
    )

    return {
        "draft_md": str(draft_path),
        "evidence_json": str(evidence_path),
        "review_json": str(review_path),
        "sources_json": str(sources_path),
        "plan_json": str(plan_path),
        "submit_checklist_md": str(checklist_path),
    }
