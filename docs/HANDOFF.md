# Implementation handoff

The approved product is the training-course maintenance application in this directory. Supplier Studio, website-repair and WordPress concepts were not resumed or modified.

## Ready to inspect

- Run the local application with the README command.
- Read the two synchronized READMEs and `CONTRACT.md`.
- Inspect `evidence/beacon-maintained.course.zip` (actual browser workflow) and `evidence/beacon-recovered.course.zip` (separate abrupt-interruption/recovery run).
- Match the recovered artifact's SHA-256 with `evidence/recovery-proof.json`; the browser and recovery runs intentionally have different task IDs and artifacts.
- Inspect five real screenshots in `docs/screenshots/`, `evidence/browser-check.json`, and `docs/VALIDATION.md`.

## Completed acceptance scope

The trainer can input their own Markdown/text, quiz and images without authoring IDs or JSON, then manually propose, review, apply and export updates. The synthetic case preserves rejected button text and unaffected chapters, resolves contradictory retention evidence with an explicit human reason, updates the quiz answer/explanation while keeping the 20MB distractor, and works in an independent learner browser after the author server stops.

Deterministic checks cover approval persistence, writes interrupted before/after commit and partial file materialization, export interrupted before its completion receipt, duplicate actions, source changes, real external target edits, rollback, invalid archives/media/answers, missing/false citations and broken internal links. The service refuses silent success for these failures.

## Critical unfinished verification

**This is not yet a live-connected autonomous AI maintenance agent.** The real server adapter is present but disabled. No provider was called and no keys were read or persisted. Live influence identification, unseen-course reasoning, semantic consistency and model prompt-injection resistance remain unverified. Human-authored fixtures and protocol stubs do not close that gap. A separately authorized execution method is required for that next milestone.

The managed browser denied `file://`; the policy was not bypassed. Independent local-static-origin delivery, embedded assets and offline interaction were verified. Direct double-click opening, other operating systems, and a second physical machine remain unverified.

## Boundaries kept

Only the new standalone directory was used. No old user repository, GitHub account or remote repository was accessed. No remote repository, deployment, paid call or external message/write was created. No real learner data was used. The task creation receipt supplied by the parent remains `gpt-6-astra / xhigh / fast`, admitted as `started`; there was no observed model mismatch or deliberate model change.

Local commits use author/committer `zhukewei` and the email verified from existing global Git configuration (`kewei.zhu@outlook.com`). No remote or final product repository name is selected here; that remains with the parent after review.
