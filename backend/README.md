# AI Sana Challenge Hub — backend

Step 8: Source-grounded execution stress tests, adaptive AI interviews and knowledge
maps, alongside deterministic readiness, publishing, catalog, manual proposal
decisions, and repeatable demo data.
Requires Python 3.10+.

## Install and run

From the repository root (PowerShell):

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

On macOS/Linux, activate with `source .venv/bin/activate` instead.
If PowerShell activation is blocked, use `.\.venv\Scripts\python.exe` directly.

API docs: http://127.0.0.1:8000/docs
Health: http://127.0.0.1:8000/health

Tables are created on startup; data persists in `backend/sana.db` by default.
Optionally copy `.env.example` to `.env` and add `--env-file .env` to the
Uvicorn command. Only SQLite is supported in this MVP.
CORS allows `http://localhost:3000`.

## Endpoints

| Resource | Methods and paths |
| --- | --- |
| Health | `GET /health` |
| Tasks | `GET /api/tasks`, `GET /api/tasks/{id}`, `POST /api/tasks`, `PATCH /api/tasks/{id}` |
| Readiness | `GET /api/tasks/{id}/score`, `POST /api/tasks/{id}/confirm` |
| Execution test | `GET /api/tasks/{id}/stress-test`, `POST /api/tasks/{id}/stress-test` |
| Publishing | `POST /api/tasks/{id}/publish`, `POST /api/tasks/{id}/unpublish` |
| Catalog | `GET /api/catalog`, `GET /api/catalog/{task_id}` |
| Task proposals | `GET /api/tasks/{task_id}/proposals`, `POST /api/tasks/{task_id}/proposals` |
| Decisions | `POST /api/proposals/{proposal_id}/accept`, `POST /api/proposals/{proposal_id}/reject` |
| Teams | `GET /api/teams`, `GET /api/teams/{id}`, `POST /api/teams` |
| Proposals | `GET /api/proposals`, `POST /api/proposals`, `PATCH /api/proposals/{id}` |

Tasks accept incomplete drafts, including `{}`. Team creation requires `name`.
Proposal creation requires `task_id`, `team_id`, and `solution_idea`.
Team interests, skills, and technologies are free-text strings.
Proposal status is `pending`, `accepted`, or `rejected` (default: `pending`).
PATCH changes only supplied fields; nullable text can be cleared with `null`.
Creation returns 201; missing resources/references return 404; invalid data returns 422.
Scores and readiness levels are calculated by the server; clients cannot set them.
The frontend is in `../frontend`. AI interviews are optional; there is no authentication
or team recommendation engine. All earlier CRUD and marketplace endpoints remain available.

## Adaptive interview and knowledge map

AI structures business knowledge; it does not create business knowledge. The
interviewer extracts only explicit user statements and asks neutral questions.
It does not propose solutions, offer answer choices, confirm information, calculate
readiness, or choose teams. **AI does not calculate readiness.** The existing pure
scoring engine and explicit human confirmation endpoints remain authoritative.

Install the updated dependencies, then configure the backend environment:

```powershell
Copy-Item .env.example .env
# Edit .env locally: set OPENAI_API_KEY and, optionally, OPENAI_MODEL.
python -m uvicorn app.main:app --reload --env-file .env --host 127.0.0.1 --port 8000
```

Keep the key only on the backend, never in a `NEXT_PUBLIC_` variable. Model
configuration is centralized in `app/services/ai_interviewer.py`, defaulting to
`gpt-5.4-mini` for both interviews and execution tests. Requests use the Responses API with Pydantic structured outputs,
no tools, no provider-side response storage, and a bounded timeout. Setup follows
the official [structured output guide](https://developers.openai.com/api/docs/guides/structured-outputs).

| Interview endpoint | Behavior |
| --- | --- |
| `POST /api/tasks/{id}/interview/start` | Initialize from the existing draft or resume saved work |
| `GET /api/tasks/{id}/interview` | Retrieve the persisted questions, original sources, and knowledge items |
| `POST /api/tasks/{id}/interview/respond` | Answer a question or explicitly classify a knowledge gap |
| `POST /api/tasks/{id}/interview/retry` | Retry failed AI work using already-saved input |
| `POST /api/tasks/{id}/interview/finish` | Finish for now, at any readiness score |

Respond with `question_id`, `action`, and optional `answer`, `expert`, `source_role`.
Actions are `answer`, `dont_understand`, `dont_know`, `needs_expert`, and
`not_applicable`. Text answers are preserved verbatim. The source role and expert
name/role come from the person; the AI cannot invent them.

One additive `interview_sessions` table stores JSON state per task. Each item has
field, value, status, original source ID, source role, confirmation, question
difficulty, and optional expert. Original source texts remain alongside the items;
an AI interpretation never replaces the source record. No event-sourcing system
or knowledge-gap tables are added.

| Status | Meaning |
| --- | --- |
| OPEN | Missing information or a provided value still awaiting human review |
| UNKNOWN | The user explicitly does not know; do not keep asking |
| NEEDS_EXPERT | Another knowledgeable person is needed; preserve any supplied role/name |
| NOT_APPLICABLE | The user has explicitly verified it does not apply |
| CONFLICT | Potentially incompatible original claims; no resolution workflow |
| CONFIRMED | The matching Task value was confirmed by a human through the existing endpoint |

Question batches contain three questions when enough gaps remain and fewer near
completion. Difficulty is QUICK, THINK, DEEP, or EXPERT; at most one DEEP question
appears per batch. Questions are selected to understand the specific problem,
not to maximize points. "I don't understand" rephrases the same question without
filling a value or offering examples. "Not applicable" receives one neutral
verification question; a repeated explicit action records the classification.

Structured AI results are schema-validated, restricted to allowed fields, and
checked against original sources. Extracted values must be exact quotes from
their cited original source. Invalid, unsupported, or extra score/confirmation
properties reject the result atomically. These checks reduce invention but cannot
prove that a model has understood every quote correctly; human review is essential.

Suggestions stay in the knowledge map until the business saves a reviewed/edited
value via Task PATCH. Confirmation is a separate action through `/confirm`.
Saving a changed confirmed value still invalidates its confirmation. Classification
as unknown, needs expert, or not applicable does not itself earn points.

Completion depends on whether the problem is understood and further useful input
is available, not on reaching 100. Remaining gaps may remain classified and
unresolved. Finish for now is always available, including after AI failure.
Interview completion never gates publication.

On outage, invalid output, or missing key, the service returns saved state with a
recoverable `error`, preserving the draft and any submitted answer. It never
silently substitutes fake AI responses or questions. Retry resumes pending work.
The UI exposes both review and finish even while AI is unavailable.

## Challenge execution test

**Readiness != Executability.** Readiness measures the deterministic completeness
of human-confirmed information, using the existing 0–100 scoring rules. The
execution test diagnoses whether students have the information needed to begin
this particular challenge. **Neither predicts project success or selects a team.**

Open the business challenge's interview/review page and select **Run execution
test**. The five gates are UNDERSTAND, START, ACCESS, VALIDATE, and DELIVER. The
result shows `X/5 gates passed`, individual requirements, blockers, and
not-applicable conditions. It never produces another percentage or quality score.
Expand a requirement to see its reason, required information, knowledge status,
any user-provided knowledge owner, and the original source snapshot.

The model identifies task-specific requirements and maps evidence to them using
the dedicated `StressAIResult` schema. For each request, source-reference enums
contain only actual nonempty sources; evidence IDs are limited to current
confirmed sources. With no confirmed evidence, the schema requires empty evidence
arrays and MISSING assessments (or explicit user NOT_APPLICABLE). It does not answer a global "is this
executable?" question. The backend checks source IDs, exact quotes, field identity,
and current confirmation/status before deriving requirement and gate outcomes:

- PASS needs relevant, current confirmed evidence for that requirement. A
  confirmed statement that access is unavailable still creates a blocker.
- OPEN/unconfirmed, UNKNOWN, NEEDS_EXPERT, and CONFLICT cannot establish PASS.
  Known experts come only from stored business input, never model-generated names.
- NOT_APPLICABLE is supported by an explicit relevant knowledge classification
  or confirmed scope evidence. Missing data alone proves neither that a dataset
  is required nor that it is unnecessary. Dataset-free design tasks can therefore
  avoid a dataset blocker.
- A gate with any blocked requirement is BLOCKED. A gate whose requirements are
  all not applicable is NOT_APPLICABLE and is not counted as passed or blocked.
  Otherwise, satisfied applicable requirements produce PASS.

Requirement selection and interpretation remain model-assisted. Exact quoting
and status checks constrain the output but cannot prove every semantic inference.
The UI presents a diagnostic with source evidence, not an authoritative project
approval. No technical solutions, technologies, vendors, or implementation plans
are requested from the model.

`POST /api/tasks/{id}/stress-test` explicitly performs one model request.
`GET` returns the latest saved result without an AI call. Both return
`{task_id, result, stale, error}`; `result` is null before the first successful run.
A missing task returns 404. Invalid provider output or an outage returns a safe,
recoverable error and preserves any previous valid result.

The additive `task_stress_tests` table stores only the latest analysis and an
input fingerprint. Relevant Task content, field confirmations, knowledge
values/statuses/provenance, and the analysis version determine freshness. If they
change, GET marks the saved result stale; rerunning is always an explicit action. Publication alone
does not invalidate the analysis. Results retain their original source snapshots
so an old explanation never silently points at newly edited text.

The test does not edit Task or interview information, confirm fields, calculate
readiness, prevent publication, change proposal decisions, or select teams.
Businesses can publish challenges with blockers. No AI is rerun automatically
after edits or when opening the page.

## Publishing and catalog

Explicitly publish with `POST /api/tasks/{id}/publish`; a nonblank `title` and
`need` are required (422 otherwise). There is **no minimum readiness score** and
no confirmation requirement for publishing. Readiness and publication are separate:
improving a score never automatically publishes a task. Low-score tasks, including
drafts scoring 0, remain visible if published.

`POST /api/tasks/{id}/unpublish` removes catalog visibility without deleting the
task or its proposals. Both actions return the updated task and are repeatable.
The existing CRUD `published` flag remains supported as an explicit publication
action, subject to the same title/need validation. PATCH cannot blank title/need
on a published task; unpublish first or include `published: false` in that PATCH.

`GET /api/catalog` returns published tasks only:

- `sort=readiness` (default): score descending, then creation time descending,
  then ID descending to break ties deterministically.
- `sort=newest`: creation time descending, then ID descending.
- `industry=education`: exact, case-sensitive industry match.
- `readiness_level=draft|working|ready|priority`: exact readiness filter.
- Filters may be combined; every readiness level is accessible. Invalid sort or
  readiness values return 422. No matches returns an empty list.

`GET /api/catalog/{task_id}` returns a published task with its current `score`,
`readiness_level`, and `confirmed_fields`. Missing or unpublished tasks return 404.
The full scoring explanation remains available at `/api/tasks/{id}/score`.

## Student proposals and manual decisions

Submit through `POST /api/tasks/{task_id}/proposals`:

```json
{
  "team_id": 1,
  "solution_idea": "Build a demand dashboard",
  "plan": "Analyze sales and build a demo",
  "timeline": "Two weeks",
  "prototype_url": "https://example.com/demo"
}
```

All five fields are required; text fields cannot be blank. `prototype_url` is
stored as text, without URL reachability checks. The task must be published
(409 otherwise); missing tasks or teams return 404. Submissions return 201 and
always start `pending`; the submission endpoint does not accept a status.
Any number of proposals may be submitted, including repeat submissions by a team.
`GET /api/tasks/{task_id}/proposals` lists that task's proposals by ID ascending,
including after unpublishing, and returns 404 if the task does not exist.

Businesses manually call `POST /api/proposals/{proposal_id}/accept` or `/reject`.
These return the updated proposal; unknown proposals return 404. Decisions can be
repeated or reversed. Accepting one proposal never rejects or changes another.
A business may accept one team, multiple teams, or no teams. **The system never
automatically selects a team.** Unpublishing preserves existing decisions.

Compatibility exception: the original generic `/api/proposals` POST/PATCH CRUD
endpoints retain Step 1 behavior, including optional plan/timeline/prototype fields,
direct manual status updates, and references to unpublished tasks. Use the new
task-scoped POST endpoint for validated marketplace submissions. With authentication
intentionally absent, this MVP does not enforce business/student permissions.

## Deterministic readiness scoring

The score describes how ready a business challenge is for student work. The pure
Python engine uses only the rules below. AI never calculates or judges the score.

| Category | Maximum | Field shares |
| --- | ---: | --- |
| Context + Need | 20 | context 10, need 10 |
| Data and Materials | 20 | data 20 |
| Expected Result | 15 | expected_result 15 |
| Success Criteria | 15 | success_criteria 15 |
| Constraints | 10 | constraints 10 |
| Users | 10 | users 10 |
| Business Connection | 10 | contact 5, interaction_format 5 |

Score = sum of the seven category scores, with a maximum of exactly 100.
Each field earns points only when meaningful **and individually confirmed**:

- Text is trimmed and whitespace collapsed. Meaningful text requires 10 characters
  (5 for contact), at least three distinct letters/digits, and at least one word.
- Case-insensitive placeholders `yes`, `no`, `none`, `test`, `n/a`, `na`, `tbd`,
  `todo`, `unknown`, and `null` earn zero. Punctuation-only text, repeated placeholder
  words, and single-character padding also earn zero.
- Confirmed meaningful descriptions of 10–29 characters receive half their field
  share, rounded down. At least 30 characters earns the full share.
- Contact earns its full 5 points when meaningful and confirmed.
- Success criteria require both 30 characters and a digit to earn 15; otherwise
  meaningful confirmed criteria earn 7. A digit is only a numeric-target heuristic,
  not proof of a useful metric. No semantic quality or contact-validity check occurs.

| Score | Level |
| --- | --- |
| 0–39 | draft |
| 40–69 | working |
| 70–89 | ready |
| 90–100 | priority |

`GET /api/tasks/{id}/score` calculates a fresh result without changing the database.
It returns `score`, `level`, seven-category `breakdown` (score/max/missing/reason),
`missing_fields`, `recommendations` (field/potential_gain/message),
`points_to_next_level`, and `next_level`. Missing fields include fields needing
confirmation or improvement; potential gains are the remaining field points.
At priority, `next_level` is null and `points_to_next_level` is 0.

## Business confirmation

Send `POST /api/tasks/{id}/confirm` with:

```json
{"fields": ["context", "need", "data"]}
```

To unconfirm, send `{"fields": ["data"], "confirmed": false}`.
The nine field names in the scoring table are the only confirmable fields.
Unknown fields, empty lists, and confirmation of meaningless values return 422.
Validation is atomic: a rejected request confirms nothing. Repeated confirmation
and unconfirmation are safe; duplicates are stored once.

`confirmed_fields` is returned with tasks and is writable only through this endpoint.
Changing a confirmed field through PATCH clears that field's confirmation. Sending
the same value preserves it; edits to other fields do not clear it. Creation,
PATCH, and confirmation synchronize stored `score` and `readiness_level`.
Direct writes to either computed field or `confirmed_fields` return 422.
The legacy task-wide `confirmed` flag remains available for CRUD compatibility;
it does not confirm individual fields or award points.

Startup upgrades existing Step 1 SQLite tables by adding `confirmed_fields`.
Existing content is preserved, but legacy client-entered scores reset to 0/draft
because those tasks have no individually confirmed fields.

## Verify

From `backend/` with the virtual environment active, run both:

```powershell
python -m unittest discover -s . -p "test_*.py" -v
python smoke_test.py
```

Unit tests cover exact level boundaries, all 512 confirmation subsets, pure and
deterministic behavior, placeholders, partial credit, and the Step 1 database upgrade.
Interview unit tests use an isolated database and mock the AI provider; adapter
tests cover missing configuration, refused/invalid responses, and safe provider
errors. No automated test spends OpenAI credits. The frontend browser suite uses
the real backend interview routes with a test-only mocked provider.
The smoke test preserves Step 1 and Step 2 checks and adds publishing, catalog,
proposal validation, independent manual decisions, and workflow persistence checks.
This starts a real Uvicorn server on a free local port and checks CRUD, defaults,
404/422 responses, CORS, and persistence across a server restart. It uses a
temporary database, leaves your development data untouched, and stops the server.

### Manual real OpenAI verification (Step 7.5)

The bounded real-model run and its findings are documented in
[REAL_OPENAI_VERIFICATION.md](REAL_OPENAI_VERIFICATION.md). This is separate from
automated regression tests and uses an isolated SQLite database.

`python verify_real_openai.py inspect` reads the local saved scenario without an
API call. To start a **new** local scenario, explicitly run
`python verify_real_openai.py start --allow-real-api`; subsequent `answer`,
`dont_know`, `dont_understand`, `needs_expert`, and `retry` actions also require
that flag. Use `--help` for arguments and the pending question's field for
`--field`. The script reads backend `.env`, requires exactly `gpt-5.4-mini`,
disables SDK retries, and caps the entire saved scenario at eight SDK attempts.
An existing scenario cannot accidentally be started twice. `inspect` is safe
after the cap; continuing paid verification requires a deliberate separate run.

The ignored `.openai-verification/` directory holds the isolated database and
sanitized synthetic transcript, including model names, source references, and
usage. The script never prints credentials or HTTP headers. Do not include it in
the automated test suite. For frontend regressions, build with
`NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` so Playwright targets its mocked backend.

### Manual real execution verification (Step 8)

Current verification status and results are recorded in
[REAL_STRESS_VERIFICATION.md](REAL_STRESS_VERIFICATION.md).

After the mocked suites pass, `verify_real_stress.py` can verify the existing
Step 7.5 golden interview against the real model. It copies that saved local
database into ignored `.stress-verification/`, preserving its original sources
and leaving both development data and Step 7.5 evidence untouched.

```powershell
python verify_real_stress.py run --allow-real-api
# Explicit verifier confirmation of the two already-provided synthetic facts:
python verify_real_stress.py confirm-known
python verify_real_stress.py run --allow-real-api
python verify_real_stress.py inspect
```

Only `run` requests AI, once per invocation. There are no automatic retries;
the saved run caps SDK attempts at four. `confirm-known` uses the ordinary PATCH
and confirmation endpoints for the existing context and need; it introduces no
new facts and is not part of the Stress Test endpoint. `inspect` only reads.
The manual runner requires the saved Step 7.5 scenario, the official OpenAI API
endpoint, and exactly `gpt-5.4-mini`; it never silently substitutes data or a model.
Use synthetic data only. The transcript contains safe model/usage information,
requirements, and source snapshots, never credentials or HTTP headers.

The recorded Step 8 verification used all four calls on the unchanged golden
scenario to investigate and correct observed model errors; it did not run
`confirm-known`. The final result passed source and semantic review. The saved
scenario's call cap is now exhausted; `inspect` remains available without cost.

## Demo data

From `backend/`, with the virtual environment active:

```powershell
python seed.py
# Explicitly replace only the seed-owned demo rows:
python seed.py --reset
```

The default database is the same `backend/sana.db` used by FastAPI. To target a
different development SQLite database, set `DATABASE_URL` in the shell first
(PowerShell: `$env:DATABASE_URL = "sqlite:///./demo.db"`). The script does not
automatically load `.env`; use the same URL for seeding and starting the server.

The fixtures contain 8 published Kazakhstan-oriented challenges, 5 student teams,
and 9 proposals. All companies, contacts, and projects are fictional. Prototype
URLs at example.com are demonstration placeholders, not hosted applications.
Preloaded accepted/rejected statuses represent fictional prior manual decisions;
the seed system does not select or rank teams.

| Challenge | Computed score | Level |
| --- | ---: | --- |
| Almaty contract review | 25 | draft |
| Shymkent student support | 20 | draft |
| Karaganda predictive maintenance | 55 | working |
| Astana bilingual support | 60 | working |
| Shymkent delivery routes | 70 | ready |
| Aktobe invoice processing | 75 | ready |
| Almaty retail forecasting | 100 | priority |
| Pavlodar employee knowledge | 100 | priority |

Scores are always calculated by the existing engine from actual field values and
individual confirmations; these numbers are documentation, not assigned scores.
Intentional gaps include unavailable contract data, unagreed student-data access,
missing metrics, unclear restrictions, and missing interaction arrangements.
Contract review, route planning, and retail forecasting have multiple proposals;
student support and employee knowledge have none. The proposal states include
pending, accepted, and rejected, with two accepted proposals on route planning.

Repeated `python seed.py` is a no-op for existing demo rows and preserves edits.
A small `demo_seed_records` table tracks exact ownership by IDs, never by names.
`--reset` transactionally replaces those rows, including edits to demo records,
while preserving unrelated tasks, teams, and proposals. Reset also refuses if a
demo task has interview history. If a non-demo proposal
references a demo task or team, reset refuses without changing data; resolve those
references deliberately before retrying. Stop concurrent writes while resetting.
Reset also refuses if demo tasks contain interview history, to preserve user answers.
No database files or application tables are dropped. Fixture timestamps and content
are fixed; numeric IDs may change when unrelated data already exists.

Seed tests cover repeatability, reset, edit preservation, unrelated data, and safe
refusal. The live smoke test also seeds its temporary database and verifies catalog
ordering, every readiness level, detail pages, computed scores, and proposal links.

## Structure

```text
backend/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── interview_schemas.py
│   ├── stress_schemas.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── catalog.py
│   │   ├── interview.py
│   │   ├── stress_test.py
│   │   ├── tasks.py
│   │   ├── teams.py
│   │   └── proposals.py
│   └── services/
│       ├── __init__.py
│       ├── ai_interviewer.py
│       ├── ai_stress_test.py
│       ├── interview.py
│       ├── stress_test.py
│       └── scoring.py
├── .env.example
├── .gitignore
├── demo_data.py
├── README.md
├── seed.py
├── smoke_test.py
├── test_interview.py
├── test_openai_boundary.py
├── test_scoring.py
├── test_seed.py
├── test_stress_test.py
├── test_stress_schema.py
├── verify_real_openai.py
├── verify_real_stress.py
├── REAL_OPENAI_VERIFICATION.md
├── REAL_STRESS_VERIFICATION.md
├── workflow_checks.py
└── requirements.txt
```
