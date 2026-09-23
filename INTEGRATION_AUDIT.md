# Step 10 — adversarial integration audit

Date: 2026-09-23. Starting checkpoint: **5a20bd0** (verified locally).
**DEMO SAFE: YES for the tested local, single-operator hackathon flow after fixes.**
This is not a production-readiness verdict or a guarantee of future AI semantics.
No real OpenAI calls, production-data changes, commit, or push were performed.

## Findings and reproductions

Five application defects were reproduced. All five are fixed. No BLOCKER was found.

| ID | Severity | Reproduction and observed failure | Root cause | Smallest fix and evidence |
| --- | --- | --- | --- | --- |
| A1 | HIGH | During a mocked interview generation, PATCH new human data in another request. Task retained it, but the returning AI response erased the Knowledge Map value and original source. Pausing during generation could likewise be undone. | `_generate` persisted the pre-provider interview snapshot without checking intervening writes. | Release the read transaction during the call; reload and compare the persisted interview state before saving either success or failure. Discard superseded output and preserve current sources/status; expose retry when a pending analysis remains. API regression reproduces edits, pause, and provider failure during the call. |
| A2 | HIGH | Fill a proposal, reload, and observe empty fields. After submission, reloading previously returned to a blank form, encouraging duplicate submission. | Proposal fields and success state existed only in the DOM/React memory. | Tab-scoped session storage for the draft and successful submission receipt. Same-tab refresh retains multiline original text and team. Rapid double submit produces exactly one proposal; an explicit second proposal from the same team still works. |
| A3 | MEDIUM | Enter a manual reviewed value without saving; reload or navigate away/back. The text disappeared. | Review field local state was initialized solely from the server. | Store an unsaved review draft in session storage, keyed by task/field and its original server value. Restore only when that server base still matches; never silently overwrite newer server knowledge. Regression covers reload, back navigation, save and confirmation. |
| A4 | MEDIUM | Open a public challenge, unpublish it in another request, then return focus. The page still claimed Published and offered submission. | Public detail fetched only on mount; catalog similarly did not revalidate on returning to a tab. | Refresh public reads on focus/visibility return. A now-unpublished detail shows the existing unavailable state; no polling or AI calls. Submission was already protected by backend publication validation. |
| A5 | LOW | Display a 1,500-character unbroken title and 15,000-character word in the need. The page grew wider than the viewport. | Content and grid children lacked sufficient wrapping/min-width constraints. | Apply content wrapping and zero minimum width to existing grid children. Browser assertions verify no horizontal overflow and HTML-looking input remains text, with no injected image or dialog. No visual redesign. |

Initial failing runs are real reproductions, not hypothetical findings. During
A2 repair, further checks caught a misleading restored “pending” message after
the business accepted the proposal. The receipt now states only that submission
occurred, not the current decision status, and stays visible after unpublication.
Its “Write another proposal” action is disabled when the public challenge is
unavailable. This restores the existing ability to submit multiple proposals.

Intermediate test failures also exposed text-label matching after restored
textarea values and double-click probes firing before controls became enabled.
Stable accessible labels and explicit enabled-state preconditions were added;
the repeated clicks themselves still execute twice in the same browser task.
The final complete suites passed after these corrections.

## Scenario coverage

| Requested audit | Execution and evidence |
| --- | --- |
| 1. Golden demo | Actual Next.js UI and real local FastAPI/SQLite routes with mocked providers: New Challenge, exact weak contract description, normal answer, simplify question, Unknown, IT department, save, confirm, readiness 10/100, execution blocker, publish, catalog, Student proposal, Business accept/reject, unpublish. No Swagger or API mutations substitute for these UI transitions. Read-only API assertions check saved state. |
| 2. Refresh/navigation | Reload after the normal answer, UNKNOWN, NEEDS_EXPERT, review editing, publication, proposal editing/submission and business acceptance. Back navigation preserves review text. A delayed execution POST response is interrupted by reload after server persistence; the saved result returns via GET without rerunning AI. A1 covers in-flight provider/human-edit and pause conflicts. |
| 3. Double actions | Same-task double clicks on Start interview, answer, confirm, execution test, publish and proposal submission. Network assertions show one create/start, one answer per action, one confirmation, one execution run and one publish. Existing tests cover repeated/reversed decisions and independent acceptances. This is UI protection, not a distributed idempotency guarantee. |
| 4. AI failures | Existing start-outage/browser retry and stress outage/preserved-result tests; new API cases for timeout, malformed JSON and outage after an answer. Original answer sources and score survive; safe errors and explicit retries work. No invented fallback questions. |
| 5. Knowledge integrity | UNKNOWN and NEEDS_EXPERT later receive explicit human edits, can be confirmed, and preserve prior action sources. Editing confirmed data clears confirmation and recalculates score; data and success-criteria changes stale the saved execution test. A1 specifically verifies Task/Knowledge Map consistency under an intervening edit. |
| 6. Publication | UI publication at 0 and 10 with incomplete knowledge; UNKNOWN/NEEDS_EXPERT and execution blockers remain allowed. Existing HTTP checks cover published edits and required fields. Unpublish/republish changes catalog visibility, not readiness or prior proposals. Saved stress result is unchanged by publication. |
| 7. Catalog | All four filters and score ranges, readiness/newest ordering, industry filter, empty results and direct missing/unpublished URLs. A4 tests an already-open challenge becoming unpublished. No idle polling observed. |
| 8. Proposals | Low-readiness submission, two proposals from the same team, multiline Unicode originals, HTTP(S) URL validation, independent multiple acceptances, reject/reversal, refresh after decision, and unpublication after submission. Original text is preserved byte-for-byte at the JSON string level. No automatic winner. |
| 9. Input edges | Empty, whitespace and punctuation confirmations rejected; duplicate confirmation fields deduplicated. English/Russian/Kazakh/emoji, 20,000-character input, HTML/Markdown-looking text, malformed JavaScript URL, and long unbroken layout inputs. API legacy URL storage remains intentionally more permissive than the submission UI. |
| 10. Language | Mocked interview processes original Russian/Kazakh sources and Russian structured questions through actual validation/persistence. Browser proposal/review text includes Kazakh/Russian/emoji. No English-only schema/storage blocker found. This does not verify live-model translation or question quality. |
| 11. Clean start | Copied Git-visible backend files to a disposable folder, copied safe env example, verified no initial DB, ran seed then Uvicorn with `--env-file`. Health/catalog passed with 8 tasks, 5 teams, 9 proposals and all four readiness levels. Existing installed Python dependencies were reused; `pip check` passed. Browser suites independently start production Next.js and a fresh seeded API. No fresh OS/package-download installation is claimed. |
| 12. Frontend failures | Existing browser coverage exercises backend outage, delayed catalog, 404, empty catalog, interview failure and execution failure. Publication failure preserves edits and is retryable. No tested failure produced a blank page. |
| 13. Secret/log safety | Provider-boundary regressions and raw-error sentinel checks ensure private provider failure text is not returned in API errors. Regression subprocesses use blank API keys and mocked providers. Git-visible contents/history and ignore rules rechecked without printing credentials; no configured-key or common credential-pattern matches. |
| 14. Performance sanity | UI request counts confirm no AI run from reload, publication or passive rendering. Catalog remains idle between user actions. Production JS totals about 663 KB raw / 204 KB gzip across all 16 chunks, largest about 229 KB raw; this is not per-page transfer size. No accidental huge asset, loop or periodic AI polling found. No load test. |

## Final verification

| Check | Final result |
| --- | --- |
| Full backend unittest/API suite | **96/96 passed** (7 new adversarial tests) |
| Live HTTP smoke suite | **206/206 passed** |
| Full Playwright browser suite | **27/27 passed** (6 new adversarial tests; existing golden test strengthened) |
| Next.js production build | **Passed** |
| TypeScript `tsc --noEmit` | **Passed** |
| Python dependency consistency | **Passed** |
| Complete golden UI flow again after full regression | **1/1 passed** |

Totals: **123 distinct automated test cases and 206 HTTP checks**. The final
golden rerun is an additional execution of an existing case, not another unique
test. Mock subcases and assertions are not inflated into separate test totals.
Real OpenAI calls in Step 10: **0**.

Commands remain those in the root README. To repeat just the final UI journey:

```bash
cd frontend
npm run test:e2e -- tests/zzz-publication.spec.ts -g "golden flow"
```

Build first, install Google Chrome, and keep ports 3000/8000 free. Test servers
use temporary databases and mock both AI providers before starting FastAPI.

## Remaining risks and verdict

- Authentication, ownership enforcement, production infrastructure and distributed
  write coordination are deliberately absent. This audit verifies one operator's
  UI and a targeted intervening-request race, not all simultaneous multi-user or
  multi-worker schedules. No transactional global locking system was added.
- A network interruption after a proposal reaches the server but before its
  response remains an uncertain outcome. The UI warns before retry; no automatic
  retry or server idempotency key was introduced. Check the business proposal list
  before resubmitting an uncertain request.
- Session storage recovers drafts only within the browser tab/session when
  storage is available. A closed tab, cleared storage, or blocked browser storage
  can lose unsaved text. A review draft whose base was changed elsewhere is not
  applied over the newer server value. Use a fresh private window when resetting
  demo databases to avoid reusing task IDs with old browser-local drafts/receipts.
- Public data refreshes on navigation/focus, not continuously. An open foreground
  page may show old data until refreshed; the server still rejects submissions to
  unpublished tasks. Focus/visibility can cause a small bounded number of GETs.
- Semantic model correctness and neutrality are not proven by mocked tests.
  Prior bounded real-model reports remain the available evidence; no new paid
  verification was performed. Human review, explicit confirmation and rejection
  of unverifiable output remain necessary.
- The clean-start check reused installed dependencies on Windows. macOS/Linux
  instructions and external package availability were not executed on a fresh OS.

**DEMO SAFE: YES**, within those explicit local-demo limits. This verdict is based
on reproduced failures being repaired, persistence/source checks, failure recovery,
and a final complete UI journey, not merely green happy-path totals. There are
**no unresolved BLOCKER or HIGH defects found in the tested scope**. Do not treat
this as authorization to expose the unauthenticated MVP publicly.
