"""Conservative, persisted citation-location checks for source revisions."""
from difflib import SequenceMatcher, unified_diff


def _occurrences(text, quote, limit=6):
    """Count raw quote occurrences and retain a few line-aligned locations."""
    found = []
    cursor = 0
    count = 0
    while count < limit:
        offset = text.find(quote, cursor)
        if offset < 0:
            break
        count += 1
        end = offset + len(quote)
        at_line_start = offset == 0 or text[offset - 1] == "\n"
        at_line_end = end == len(text) or text[end] == "\n"
        if at_line_start and at_line_end:
            start_line = text.count("\n", 0, offset) + 1
            found.append({"start_line": start_line, "end_line": start_line + quote.count("\n")})
        cursor = offset + 1
    truncated = count == limit and text.find(quote, cursor) >= 0
    return {"count": count, "truncated": truncated, "ranges": found}


def _citation_location(citation, old_source, new_source, line_map):
    quote = citation["quote"]
    old_hits = _occurrences(old_source, quote)
    new_hits = _occurrences(new_source, quote)
    old_range = {"start_line": citation["start_line"], "end_line": citation["end_line"]}
    result = {
        "old_range": old_range,
        "new_ranges": new_hits["ranges"],
        "match_count": new_hits["count"],
        "matches_truncated": new_hits["truncated"],
    }
    if old_hits["count"] != 1:
        result["status"] = "ambiguous"
        return result
    if not old_hits["ranges"] or old_hits["ranges"][0] != old_range:
        result["status"] = "old_mismatch"
        return result
    if new_hits["count"] == 0:
        result["status"] = "removed"
        return result
    if new_hits["count"] > 1:
        result["status"] = "ambiguous"
        return result
    if not new_hits["ranges"]:
        result["status"] = "changed"
        return result

    new_range = new_hits["ranges"][0]
    result["new_range"] = new_range
    old_start = citation["start_line"] - 1
    old_end = citation["end_line"]
    new_start = new_range["start_line"] - 1
    quote_lines = quote.splitlines()
    old_line_count = len(old_source.splitlines())
    new_line_count = len(new_source.splitlines())

    if old_start < 0 or old_end > old_line_count or len(quote_lines) != old_end - old_start:
        result["status"] = "old_mismatch"
        return result
    if any(line_map.get(index) != new_start + index - old_start for index in range(old_start, old_end)):
        result["status"] = "context_changed"
        return result

    # The citation must keep the same file-boundary relationship as well as
    # one unchanged adjacent line on each side. Added context at a former
    # boundary can change meaning even when the exact quote remains unique.
    if (old_start == 0) != (new_start == 0):
        result["status"] = "context_changed"
        return result
    if (old_end == old_line_count) != (new_start + len(quote_lines) == new_line_count):
        result["status"] = "context_changed"
        return result
    if old_start > 0 and line_map.get(old_start - 1) != new_start - 1:
        result["status"] = "context_changed"
        return result
    if old_end < old_line_count and line_map.get(old_end) != new_start + len(quote_lines):
        result["status"] = "context_changed"
        return result

    result["status"] = "unchanged" if new_start == old_start else "moved"
    return result


def create_source_review(old_source, new_source, proposals, current_targets, before_hash, after_hash):
    old_lines = old_source.splitlines()
    new_lines = new_source.splitlines()
    line_map = {}
    matcher = SequenceMatcher(None, old_lines, new_lines)
    for tag, old_start, old_end, new_start, _ in matcher.get_opcodes():
        if tag == "equal":
            for index in range(old_start, old_end):
                line_map[index] = new_start + index - old_start

    source_diff = list(unified_diff(
        old_lines, new_lines, fromfile="此前资料", tofile="更新资料", lineterm="", n=2
    ))
    checks = {}
    for proposal in proposals:
        body = proposal["body"]
        citations = [
            _citation_location(citation, old_source, new_source, line_map)
            for citation in body.get("citations", [])
        ]
        statuses = {citation["status"] for citation in citations}
        if not citations:
            citation_status = "missing"
        elif "ambiguous" in statuses:
            citation_status = "ambiguous"
        elif "context_changed" in statuses:
            citation_status = "context_changed"
        elif "removed" in statuses:
            citation_status = "removed"
        elif "changed" in statuses:
            citation_status = "changed"
        elif "old_mismatch" in statuses:
            citation_status = "old_mismatch"
        elif "moved" in statuses:
            citation_status = "moved"
        else:
            citation_status = "unchanged"

        target = current_targets.get(proposal["target_id"])
        reasons = []
        if proposal["status"] == "stale" or proposal["source_hash"] != before_hash:
            reasons.append("already_stale")
        elif proposal["status"] not in {"approved", "pending"}:
            reasons.append("status_requires_full_review")
        if body.get("requires_resolution"):
            reasons.append("known_conflict")
        if proposal["errors"]:
            reasons.append("proposal_errors")
        if not target or target["digest"] != body.get("expected_digest"):
            reasons.append("target_changed")
        if not citations:
            reasons.append("missing_citation")
        if any(status == "ambiguous" for status in statuses):
            reasons.append("nonunique_citation")
        if any(status == "context_changed" for status in statuses):
            reasons.append("citation_context_changed")
        if any(status in {"removed", "changed", "old_mismatch"} for status in statuses):
            reasons.append("citation_changed")

        checks[proposal["id"]] = {
            "target_id": proposal["target_id"],
            "from_status": proposal["status"],
            "citation_status": citation_status,
            "citations": citations,
            "quick_reconfirm": not reasons,
            "full_review_reasons": reasons,
        }

    added = sum(1 for line in source_diff if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in source_diff if line.startswith("-") and not line.startswith("---"))
    return {
        "before_hash": before_hash,
        "after_hash": after_hash,
        "diff": source_diff,
        "added_lines": added,
        "removed_lines": removed,
        "proposal_reviews": checks,
        "note": "Locator status checks exact line placement and adjacent context only; it does not establish semantic support. Every prior approval remains stale until a person explicitly reconfirms it.",
    }
