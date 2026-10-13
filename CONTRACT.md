# First-version contract

This is a local course maintenance application. It does not create new training material autonomously while AI is disabled. Trainers can paste/import Markdown or plain text, add questions with ordinary form fields, and attach local images; the application generates all stable IDs and the reusable package. No handwritten JSON or IDs are required.

## Inputs

- A `.course.zip` containing `course.json`, `source.md` (the previous approved reference), and optional PNG/JPEG/WebP files beneath `assets/`.
- A new UTF-8 Markdown reference, up to 100 KB. Markdown is displayed as text with stable line numbers and a SHA-256 version.
- Course schema version `1`: course ID, title, language, chapters with globally unique IDs, text blocks, and single-answer multiple-choice questions. Each chapter contains at least one text block. Images use package-relative asset paths. Arbitrary HTML, executable files, remote assets, PPTX and PDF are unsupported.
- Up to 30 chapters, 300 editable items, 20 MB uncompressed package data, 100 files and 4 MB per image. Archive traversal, links, duplicate paths and oversized entries are rejected before extraction.

## Proposal contract

Each proposal identifies one existing text block or complete quiz object, the expected digest of that object, a replacement of the same type, rationale, and exact line citations into the new reference. Missing citations and conflicting targets are shown as blocked or competing proposals, never silently approved. Citation syntax is validated deterministically; semantic support remains an AI/human judgment.

Approvals are bound to the proposal, current target, and source version. Material source changes invalidate unapplied approvals. Changes already applied against an older source require explicit review before exporting a package advertised as current. Unaffected course objects are preserved exactly.

## Modes

1. **Offline review:** humans enter proposals or import explicitly labeled, human-authored demonstration proposals. These exercise the real review/apply/export/recovery pipeline and never count as AI analysis.
2. **Optional AI:** an OpenAI-compatible server adapter requests schema-constrained proposals. Live calls are disabled by default. Session configuration is memory-only, excludes secret persistence and is never filled from local keys. Enabling it later requires a permitted provider and budget; the current implementation task does not authorize live calls.

## Outputs

An updated reusable `.course.zip`, a standalone interactive `course.html`, complete updated course JSON, included local media, and human-readable/machine-readable change records. The HTML contains no remote dependencies and works in a fresh browser without original browser storage. Quiz feedback is derived from the exported answer key, with a clear warning that client-side quizzes are learning aids, not secure examinations.

## State and recovery

SQLite is the durable authority. Each target update and proposal receipt share one transaction. A task's actual `course.json` is materialized atomically from committed state. Approval replay and apply replay are idempotent. A batch retains its pre-apply snapshot for rollback. Uncertain responses are resolved by reading durable state, not by blindly repeating writes. Files are local and no real learners are involved.

## Acceptance

- Review exact old/new values, source line citations, impact scope, missing evidence and competing suggestions.
- Apply only individually approved proposals; preserve rejected/unaffected objects exactly; validate quiz choices/answer keys and asset references.
- Interrupt before a write, after durable commit/before acknowledgement, and while awaiting approval; resume without duplicate or lost changes.
- Source changes invalidate stale approvals and prevent a falsely current export; malformed input leaves existing tasks unchanged.
- Independently open the exported course in a fresh browser, answer a question, exercise links/images, and confirm zero external resource requests.
- Real AI integration remains explicitly unverified until an authorized live execution has occurred. Offline checks do not close that gap.
