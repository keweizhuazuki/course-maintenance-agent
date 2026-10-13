[简体中文](README.zh-CN.md)

# Course Maintenance · 课续

Maintain an existing training course against revised product information. Review source-backed changes, approve or reject individual items, update real course files, and deliver a portable course with working quizzes and a printable handout.

**Status: usable local, offline human-review workflow. Real AI impact detection is not live-verified.** The default server blocks model calls and credential configuration. The built-in suggestions are explicitly human-authored synthetic fixtures, not generated AI results. Market demand and differentiation from existing course tools remain hypotheses.

![Import your own course](docs/screenshots/01-import-own-course.png)

## What works

- Paste/import your own Markdown or plain-text lesson, add multiple-choice questions and local images through forms. The app creates stable IDs and a reusable `.course.zip`; trainers do not write JSON.
- Reopen saved course packages with a new Markdown reference. Compare exact old/new text, source lines, affected chapters, conflicting evidence and missing support.
- Approve/reject each suggestion, revise suggestions, and record human conflict-resolution reasons. Questions are edited as a whole: distractors are preserved rather than globally replaced.
- Apply approved changes to durable SQLite state and an actual `course.json`. Restart, retry, and roll back the latest batch without reapplying completed edits.
- Export `course.html`, `handout.html`, `course.json`, source material, local media and readable/machine-readable change records. Rejected changes remain explicitly disclosed; the package never claims all content matches the new source.
- A real OpenAI-compatible proposal adapter is implemented, disabled by default, with memory-only configuration, no credential discovery, no automatic paid retries, and mandatory human review.

![Review changes beside exact source lines](docs/screenshots/02-source-review.png)

## Run locally

Requires Python 3.11+ and a current desktop browser. Use one local server process, bound to loopback. No account or remote repository is needed. Dependency installation requires ordinary package access; no model service is used by these commands.

**Linux / macOS**

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

**Windows PowerShell**

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`. The interface is Simplified Chinese. Linux/Chromium was tested; Windows and macOS instructions have not been executed in this task. The app is single-user and local-only; it is not a hosted multi-tenant service.

## Your first course

1. Choose **从讲义建立课程**. Enter a title and paste/import `.md` or `.txt`. `## Heading` starts a chapter; blank lines separate text blocks. This is explicit format conversion, not semantic AI parsing.
2. Optionally add questions with 2–6 choices, one answer and an explanation; attach PNG/JPEG/WebP images and descriptions. Select the relevant chapter in the form.
3. Paste/import the revised reference and create the task. Add your own changes with **人工添加修改**, select source lines, then review and approve them. There is no offline automatic impact analysis.
4. Apply approved items, resolve/reject remaining suggestions, and download the course/handout package. Reopen that package for the next maintenance cycle.

PPTX, PDF, arbitrary HTML, videos, remote media, SCORM/LMS integration and secure exams are not supported. Markdown is a deliberately limited text/heading/link format; it is not a full renderer. See [the exact contract](CONTRACT.md).

## Demonstration and reviewable artifacts

Open **Beacon Desk** and explicitly load **人工演示建议**. Approve 50MB capacity changes and the quiz; choose 14 days with a reason addressing the conflicting 21-day memo; reject the two button renames. The result keeps `Export data`, preserves the `20MB` distractor, and changes the correct answer to C=`50MB` with the matching explanation. Two unrelated chapters remain byte-for-byte equivalent at the data-object level.

- [Actual exported synthetic course](evidence/beacon-maintained.course.zip)
- [Browser acceptance record](evidence/browser-check.json)
- [Recovery evidence](evidence/recovery-proof.json)
- [Validation report and limits](docs/VALIDATION.md)

![Exported course in an independent browser](docs/screenshots/04-independent-offline-course.png)

Unzip the artifact. On a browser that permits local files, `course.html` is designed as a self-contained document. **Direct double-click/file-URL opening was blocked by this environment's browser policy and remains unverified.** The verified delivery mode is a separate local static server, independent of the authoring application:

```sh
python -m http.server 8766 --bind 127.0.0.1 --directory path/to/extracted-course
```

Open `http://127.0.0.1:8766/course.html` or `handout.html`. The acceptance run stopped the author server, used a new browser process/profile, loaded these pages from their own static origin, then disabled network access for image/quiz interaction. No external resource requests were made. The HTML embeds media; it does not depend on the author browser's cache. Quizzes are client-side learning aids; answers are inspectable and no learner results are transmitted.

## Recovery and safety boundaries

Local task state is in `.local/`. Keep this directory to resume; deleting it removes tasks. SQLite is authoritative. Each target change and its applied receipt are committed together; `course.json` is materialized atomically. A known interrupted materialization can be repaired. Unrecognized external edits are preserved and block writes; related approvals are invalidated. To continue, restore the service-owned file from your backup or start a new task incorporating the external edits—there is no automatic merge.

New reference text conservatively invalidates **all unapplied suggestions**, while already-applied targets require new review before a current export. Rejected decisions remain visible. This is deliberately stricter than semantic change localization; unaffected chapters are never automatically rewritten. Export is blocked by unresolved suggestions, stale applied evidence, broken internal links or missing/corrupt supported media. External links are labeled unverified rather than fetched. Text citation validation does not establish factual entailment.

## Optional real AI path — not exercised

Only after obtaining independent provider/budget authorization, start a fresh local server with `COURSE_ALLOW_LIVE_AI=1`, open **AI 连接状态**, and supply an explicit OpenAI-compatible base endpoint (ending in `/v1`), model and temporary key. HTTPS endpoints and explicit loopback HTTP model endpoints are accepted. The app appends `/chat/completions` and requires structured JSON responses. Compatibility with any specific provider is not established.

The key stays only in server memory, is not returned to the UI or written to task records, and disappears on clear/restart. No `.env`, old workspace, chat history or local credential file is searched. Live calls send the course and both references to the configured provider; use only data authorized for that destination. Provider errors do not trigger automatic retries. No real AI calls, paid calls or PackyAPI calls were made during this implementation. Protocol transport stubs test parsing only, not reasoning, impact detection or resistance to prompt injection.

## Reproduce checks

```sh
python -m unittest discover -s tests -v
python scripts/recovery_proof.py
python scripts/browser_check.py
```

The browser check additionally requires Playwright and Chromium (`requirements-dev.txt`). It uses `/usr/bin/chromium` when present, otherwise Playwright's installed Chromium; set `COURSE_CHROMIUM` to choose a specific browser. GitHub Actions runs these checks on pushes to `main` and pull requests; the workflow uses synthetic data and needs no secrets. Browser checks use independent temporary task stores and loopback HTTP. [Screenshots](docs/screenshots/) are actual captures of this application and exported artifacts.

## Next / not yet proven

Run authorized real AI influence detection on unseen courses; evaluate citation entailment, source conflict detection and source-instruction attacks. Compare an actual trainer's recurring maintenance task against existing tools. Improve selective approval invalidation only after those semantics can be checked. Rich document import, LMS delivery, grading services, multi-user authentication and deployment are outside this first version. No old user repository was inspected.
