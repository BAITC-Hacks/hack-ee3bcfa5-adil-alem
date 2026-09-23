# AI Sana Challenge Hub — marketplace

Next.js App Router, TypeScript, and Tailwind CSS marketplace frontend. Requires
Node.js 20.9+ and npm. No external fonts, image services, or state libraries.

## Run locally

Start and seed the backend following `../backend/README.md`. From `frontend/`:

```powershell
npm install
Copy-Item .env.example .env.local
npm run dev
```

Open http://localhost:3000 (this origin is permitted by backend CORS).
On macOS/Linux use `cp .env.example .env.local`.
`NEXT_PUBLIC_API_URL` defaults to `http://127.0.0.1:8000`; set it before building
for a different API. Requests originate in the browser, so its API origin must
be reachable from the browser and permitted by backend CORS.

## Pages and behavior

- `/` and `/challenges`: public catalog, industry/readiness filters, and readiness/newest ordering.
- `/challenges/[id]`: published challenge fields and score breakdown.
- `/challenges/[id]/propose`: explicit team selection and original proposal submission.
- `/business`: all challenge records with publication status and review links.
- `/business/challenges/[id]/proposals`: original submissions and manual decisions.
- `/business/new`: an original free-text business draft, with an optional title.
- `/business/challenges/[id]/interview`: adaptive interview, knowledge map, original
  sources, editable field review, explicit human confirmation, and execution test.
- The Student/Business demo switcher changes navigation only. It provides no
  authentication, security, or ownership checks. My Proposals remains marked Soon.

The typed client in `lib/api.ts` calls `/api/catalog`, `/api/catalog/{id}`, and
`/api/tasks/{id}/score`. Filters and sorting are sent to the backend. An unfiltered
catalog request supplies available industries. Cards omit proposal counts because
they are not part of the catalog response. Missing fields are explicitly unknown;
provided but unconfirmed values are labeled separately. All published readiness
levels are shown by default. Loading, retryable connection errors, empty results,
unavailable score breakdowns, and missing/unpublished challenge states are handled.

## Proposals and business decisions

Teams come from `GET /api/teams`; none is selected by default. The submission form
shows the challenge title, readiness, expected result, and constraints. Missing or
unconfirmed information is labeled; low readiness never blocks submission.
Team, solution idea, plan, timeline, and an HTTP(S) prototype URL are required.
Submissions use `POST /api/tasks/{id}/proposals`. While submitting, controls are
disabled. Errors retain the entered text. Success shows a pending confirmation and
links back to the challenge/catalog. An uncertain network result is not retried
automatically because the backend does not provide idempotency keys.

The business dashboard uses `GET /api/tasks`; review uses `GET /api/tasks/{id}`,
`GET /api/tasks/{id}/proposals`, and the team list. Original text is rendered directly
with line breaks preserved in a dedicated OriginalProposal component. No summaries
or AI explanations are generated. Historical nullable fields display Not provided.
Prototype links open separately and only HTTP(S) URLs are clickable.

Accept and Reject call the existing `/api/proposals/{id}/accept` and `/reject`
endpoints. Only the returned proposal changes on screen. Multiple proposals can
remain accepted; decisions can be reversed. Proposals appear in backend submission
order, without rankings. The business always makes the final decision.

## Business knowledge interview

Choose **New challenge** in the business workspace. The original description is
saved in a Task before analysis starts. The form also keeps a browser-local draft;
if the AI is unavailable or the page is reloaded, the saved challenge can be
continued. Browser storage is a convenience, not authentication; use this demo on
a trusted development machine. Previously created challenges have a **Clarify
challenge** link in the workspace.

The frontend calls the task's `/interview/start`, `/interview/respond`,
`/interview/retry`, `/interview/finish`, and `GET /interview` endpoints. Configure
`OPENAI_API_KEY` and the model **in the backend environment only**, as documented
in `../backend/README.md`. Never put OpenAI credentials in `NEXT_PUBLIC_*` variables
or frontend files. OpenAI calls, Pydantic output validation, question batching, and
knowledge persistence happen on the backend.

The interface presents a small question batch with difficulty labels. It offers
explicit **I don't understand**, **I don't know**, **Needs another expert**, and
**Not applicable** actions rather than inferring these states from vague prose.
An optional contributor role and an optional expert name/role are retained as
provided. Questions can be simplified without suggesting answers. A not-applicable
claim may receive one neutral verification question. No expert invitation is sent.

The knowledge map distinguishes provided, confirmed, unknown, needs-expert,
not-applicable, open, and conflicting information. Provided values are unconfirmed
interpretations. Original contributions and their recorded roles are available
beside each interpreted field and in **Original words and sources**. Missing facts
remain missing. AI does not invent information, propose solutions, choose teams,
or calculate readiness.

**Save reviewed value** uses the existing Task PATCH endpoint. It does not confirm
the value. A separate **Confirm field** action calls the existing confirmation
endpoint; only that human action can award deterministic readiness points.
Unresolved items cannot be confirmed until known information is explicitly supplied.
Editing a previously confirmed field removes its confirmation under the existing
backend rules. There is no extra progress percentage or target score.

**Finish for now** preserves the interview and leaves remaining uncertainty
visible. It is available even after an AI error and below 100 readiness. Completion
is about understanding the problem and classifying remaining gaps, not maximizing
the score. The user can resume later. Interview status does not restrict publishing.
An AI failure shows a recoverable error and **Retry AI**, preserving saved answers;
the frontend never substitutes made-up questions. In-flight typed answers are kept
in browser storage so they also survive a page reload.

## Challenge execution test

The interview/review page also has **Marketplace publication** with readiness,
current execution blockers (when verified fresh), and known unresolved knowledge.
Save the title explicitly if needed; save business need in Human review.
**Publish challenge** uses the existing `/api/tasks/{id}/publish` endpoint and
shows **Challenge published**, **Published**, and **View in catalog** on success.
**Unpublish** uses `/api/tasks/{id}/unpublish`. Missing title/need produces a clear
error without filling values. No minimum readiness or blocker restriction is
added. Publication changes no confirmation or readiness and triggers no AI or
automatic execution rerun. A failed request preserves edits and can be retried.

Open **Clarify challenge** in the business workspace, then select **Run execution
test**. This explicit action calls `POST /api/tasks/{id}/stress-test`; simply
opening the page calls `GET` to retrieve the saved latest result without rerunning
AI. An interview does not need to have started first.

The panel shows five gates (UNDERSTAND, START, ACCESS, VALIDATE, DELIVER), the count
of gates passed, and blockers. Expand a gate to see its task-specific requirements,
reasons, required information, knowledge status, and any user-provided knowledge
owner. **Show source information** reveals the source snapshot used for that test.
NOT_APPLICABLE is displayed explicitly and never presented as a blocker.

**Readiness is not executability.** Readiness is deterministic completeness of
human-confirmed information. The execution test is a source-grounded diagnostic
of whether students can begin with the available information. It has no percentage
or quality score. Neither predicts project success or selects a team. Blockers
do not prevent publication, change readiness, confirm fields, or affect proposals.

Saving, confirming, and interview actions refresh the saved test with a GET.
Returning to the browser tab also checks freshness. Relevant changes show a stale
notice and retain the prior source snapshot. **Run execution test again** is
always explicit; editing never automatically spends AI credits. Loading errors
state that freshness is unverified, and provider errors preserve any previous
result with an explicit retry. AI credentials stay entirely on the backend.

## Verify

```powershell
npm run build
npm run typecheck
npm run test:e2e
```

Browser tests require installed Google Chrome, installed backend dependencies,
and free ports 3000/8000. They start the production frontend and FastAPI themselves,
then stop both. `tests/serve_backend.py` creates and seeds an isolated temporary
SQLite database; test submissions and decisions never touch development data.
Build with the default API URL for these local tests.
Failure/empty/loading states are simulated only inside browser tests. Screenshots
are saved under ignored `test-results/`. Test browser selection is in
`playwright.config.ts` if Chrome is unavailable on your machine.

Tests cover the original catalog checks plus submission, validation, original-text
preservation, manual decisions, multiple acceptances, role switching, and API errors.
Execution tests mock only the provider in the isolated backend and cover five-gate
display, blocker/source expansion, known experts, not-applicable requirements,
unchanged readiness/confirmations, publication with blockers, staleness, explicit
reruns, and recoverable provider errors. Automated runs use no OpenAI credits.

Structure: `app/` routes and styling; `components/` catalog, detail, readiness,
proposal form, original proposal review, dashboard, demo navigation, and feedback
states; `lib/` API types/client; `tests/` browser verification.

Framework setup follows the official [Next.js installation guide](https://nextjs.org/docs/app/getting-started/installation)
and [Tailwind Next.js guide](https://tailwindcss.com/docs/installation/framework-guides/nextjs).
