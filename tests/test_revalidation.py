import unittest
from copy import deepcopy

from app.revalidation import create_source_review


OLD = "Policy title\nThe service supports 12 hours.\nExisting qualification.\n"
QUOTE = "The service supports 12 hours."


def make_proposal(status="approved", source_hash="before", resolution=False):
    return {
        "id": "proposal-1",
        "target_id": "target-1",
        "status": status,
        "source_hash": source_hash,
        "errors": [],
        "body": {
            "expected_digest": "target-digest",
            "citations": [{"start_line": 2, "end_line": 2, "quote": QUOTE}],
            "requires_resolution": resolution,
        },
    }


def inspect(old_source=OLD, new_source=OLD, proposal=None, target_digest="target-digest"):
    proposal = proposal or make_proposal()
    review = create_source_review(
        old_source,
        new_source,
        [deepcopy(proposal)],
        {"target-1": {"digest": target_digest}},
        "before",
        "after",
    )
    return review["proposal_reviews"]["proposal-1"]


class RevalidationLocatorTests(unittest.TestCase):
    def test_unique_quote_can_be_located_after_move_with_both_neighbors_unchanged(self):
        check = inspect(new_source="Revision note\n\n" + OLD)
        self.assertEqual(check["citation_status"], "moved")
        self.assertEqual(check["citations"][0]["status"], "moved")
        self.assertEqual(check["citations"][0]["match_count"], 1)
        self.assertEqual(check["citations"][0]["new_range"]["start_line"], 4)
        self.assertTrue(check["quick_reconfirm"])

    def test_changed_or_removed_quote_requires_full_review(self):
        check = inspect(new_source=OLD.replace("12 hours", "8 hours"))
        self.assertEqual(check["citations"][0]["status"], "removed")
        self.assertIn("citation_changed", check["full_review_reasons"])
        self.assertFalse(check["quick_reconfirm"])

    def test_quote_with_changed_line_boundary_requires_full_review(self):
        new_source = OLD.replace(QUOTE, QUOTE + " New qualification.")
        check = inspect(new_source=new_source)
        self.assertEqual(check["citations"][0]["status"], "changed")
        self.assertIn("citation_changed", check["full_review_reasons"])
        self.assertFalse(check["quick_reconfirm"])

    def test_duplicate_quote_is_ambiguous_and_requires_full_review(self):
        check = inspect(new_source=OLD + "\n\n" + QUOTE + "\n")
        self.assertEqual(check["citations"][0]["status"], "ambiguous")
        self.assertEqual(check["citations"][0]["match_count"], 2)
        self.assertIn("nonunique_citation", check["full_review_reasons"])
        self.assertFalse(check["quick_reconfirm"])

    def test_changed_adjacent_context_requires_full_review(self):
        new_source = OLD.replace("Policy title\n", "Policy title\nNew qualification.\n")
        check = inspect(new_source=new_source)
        self.assertEqual(check["citations"][0]["status"], "context_changed")
        self.assertIn("citation_context_changed", check["full_review_reasons"])
        self.assertFalse(check["quick_reconfirm"])

    def test_new_context_at_old_file_boundary_requires_full_review(self):
        old_source = QUOTE
        proposal = make_proposal()
        proposal["body"]["citations"] = [{"start_line": 1, "end_line": 1, "quote": QUOTE}]
        check = inspect(old_source=old_source, new_source="New preface\n" + QUOTE, proposal=proposal)
        self.assertEqual(check["citations"][0]["status"], "context_changed")
        self.assertFalse(check["quick_reconfirm"])

    def test_conflict_changed_target_and_already_stale_proposals_cannot_quick_reconfirm(self):
        conflict = inspect(proposal=make_proposal(resolution=True))
        changed_target = inspect(target_digest="different-target")
        stale = inspect(proposal=make_proposal(status="stale", source_hash="older"))
        for check in (conflict, changed_target, stale):
            self.assertFalse(check["quick_reconfirm"])
        self.assertIn("known_conflict", conflict["full_review_reasons"])
        self.assertIn("target_changed", changed_target["full_review_reasons"])
        self.assertIn("already_stale", stale["full_review_reasons"])

    def test_pending_proposal_remains_pending_eligible_after_location_check(self):
        check = inspect(proposal=make_proposal(status="pending"), new_source="Revision note\n\n" + OLD)
        self.assertEqual(check["from_status"], "pending")
        self.assertTrue(check["quick_reconfirm"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
