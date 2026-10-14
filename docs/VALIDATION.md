# Validation and remaining gaps / 验收与剩余缺口

This record describes executed checks, not a claim that real AI analysis is connected. All course data is synthetic and all successful proposal sets in the acceptance case are explicitly human-authored.

## Executed outcomes

| Check | Observed outcome | Evidence |
|---|---|---|
| Trainer review in the actual UI | Capacity and quiz approved; 14/21-day conflict resolved with a recorded human choice; two button renames rejected | [Browser record](../evidence/browser-check.json), [review screenshot](screenshots/02-source-review.png) |
| Real course/handout update | 50MB and 14 days applied; `Export data` preserved; unrelated introduction/permission chapters unchanged | [Exported course](../evidence/beacon-maintained.course.zip), [recovery record](../evidence/recovery-proof.json) |
| Real quiz scoring | Fresh learner browser selected B=`20MB`: wrong; C=`50MB`: correct; explanation says 50MB | [Learner screenshot](screenshots/04-independent-offline-course.png) |
| Author-independent delivery | Author server stopped; separate browser process/profile; separate static origin; no external resource requests; images/interaction work after network disabled | [Browser record](../evidence/browser-check.json) |
| Persisted decisions | A new author browser context reopened all saved decisions before applying | Browser record; unit regression |
| Abrupt interruption | A child process exited with code 77 after one actual file update; a new service recovered the same batch and completed five updates | Recovery record |
| Repeated application | No additional applied events and no rewritten course file after successful repeat | Recovery record |
| Export interruption | ZIP existed before completion receipt; restart produced identical bytes and one completed export | Recovery record |
| Concurrent identical exports | A barrier forced two requests to reach atomic ZIP publication together; both returned the same valid bytes and created exactly one durable fingerprint/event. Two simultaneous browser requests also returned identical ZIPs. | [Concurrency regression](../tests/test_workflow.py), [browser record](../evidence/browser-check.json) |
| Source revision revalidation rules | All unapplied proposals start stale; unit regressions verify persisted diffs, a moved unique citation with unchanged neighbors, explicit reconfirmation without auto-apply, and full review for changed/duplicate citations, changed context, known conflict, prior staleness or changed targets | `tests/test_workflow.py`, `tests/test_revalidation.py` |
| New source after approval | Changing 50MB to 40MB invalidated five unapplied approvals without rewriting course contents | Recovery record |
| Source revalidation UI and exported course | Real macOS Chromium run: changed citation required full review; a unique unchanged citation remained stale until explicit acknowledgement; both states and the full diff survived refresh; stale export returned HTTP 409. Rejection and reconfirmation persisted; the course changed only after the separate Apply action. Course JSON, source, media, quiz, interactive HTML, print handout and change report were checked. | [Browser record](../evidence/browser-check.json), [source-review screenshot](screenshots/06-source-revalidation.png), [exported course](../evidence/customer-support-maintained.course.zip) |
| External course edit | A real external file edit was preserved; affected approval became stale while an unrelated approval stayed approved | Recovery record |
| Rollback | Restored course data exactly matched the original | Recovery record |
| Bad inputs | Archive traversal, unreadable ZIP, invalid quiz answer, corrupt image, unsupported video and invalid source rejected without mutating the existing task | `tests/test_workflow.py` |
| Missing/false evidence | Cannot approve missing citations or citations that do not equal source lines | Unit regression |
| Bad internal link | Export validation stops rather than labeling the broken course as verified | Unit regression |
| A trainer's own course | Arbitrary Markdown/text, quiz and uploaded image entered through forms; a human update was reviewed/applied without JSON/IDs | [Browser record](../evidence/browser-check.json), [course package](../evidence/customer-support-maintained.course.zip) |

## What these checks do not establish

- **Real AI impact detection, semantic entailment, automatic conflict discovery and model resistance to injected source instructions were not run.** The adapter's transport stub only checks request/response behavior. Keeping malicious source text inert in offline code does not prove a model would ignore it.
- Correct quiz option IDs are structurally validated. Whether a question, its answer and its explanation agree with revised product knowledge needs human review or a separately verified AI path. The synthetic acceptance example is correct, but this is not a general semantic guarantee.
- Direct `file://` navigation was blocked by the managed browser. The policy was not overridden. Independent local-static-origin delivery is verified; double-click opening remains unverified here.
- The separate learner browser used a fresh process/profile on the same Mac, not a second physical device. The macOS authoring and independent static-origin learner workflows ran in isolated Playwright Chromium profiles. Windows and mobile-device execution remain unverified; the user's authenticated interactive browser was not used.
- No three-minute end-to-end AI latency claim is made. Browser automation time is not a realistic training-user completion benchmark.
- No model/provider was live-called, no paid budget was consumed, and no real learner data was used. The user-supplied repository's exact public main SHA was read once; no GitHub account, unrelated/old repository, deployment or website was accessed.

## Scope decisions

Reference changes conservatively mark all unapplied proposals stale. A narrow explicit reconfirmation route is available only for a unique exact citation with unchanged line mapping and immediate neighboring context, a stable target, no recorded conflict and no proposal errors. It restores the prior pending/approved state only; a person still reviews the full diff, and nothing is automatically applied. Citation location does not establish semantic support. Unaffected chapters remain unchanged. External course edits are blocked for manual reconciliation or re-import; there is no automatic merge. Markdown/text import preserves explicit structure only. No arbitrary PPTX/PDF editing, video validation, external-link verification, LMS delivery or secure grading is claimed.

## Reproduce

Run the commands in either README. `tests/test_workflow.py` and `tests/test_revalidation.py` check deterministic invariants; `scripts/recovery_proof.py` writes a detailed abrupt-exit record; `scripts/browser_check.py` exercises the real UI and writes a fresh learner-browser record and screenshots. None require an API key. The scripts produce synthetic artifacts and temporary local task stores only. Browser evidence covers human-reviewed offline workflows, not live AI analysis or semantic entailment.
