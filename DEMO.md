# Five-minute demo runbook

## Startup

First install dependencies and create local env files using [Quick start](README.md#quick-start).
The backend key stays in `backend/.env`. From `backend/`, activate the virtual
environment and run:

```bash
python seed.py
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --env-file .env
```

In another terminal, from `frontend/`: `npm run dev`.
Open http://localhost:3000 and http://127.0.0.1:8000/docs.
Use synthetic information only. The Student/Business switcher is navigation, not login.

## Show the workflow

1. **Business → New challenge**. Title: **Contract review pilot**. Description:

   ```text
   Our employees spend too much time reviewing contracts.
   We want to automate this process.
   ```

2. Answer the need question with this explicit synthetic fact:
   “We need to identify clauses that differ from our approved contract template.”
   Use **I don't know** for unknown information and **Needs another expert** with
   **IT department** for data/access when that question appears. Do not invent
   availability to make the score rise. Questions and their order may vary.
3. Inspect **Knowledge Map** and **Original words and sources**. Save reviewed
   known values, then **Confirm field**; show readiness changing only after human
   confirmation. **Finish for now** preserves incomplete work.
4. **Run execution test**. Expand a blocker and source information. Explain:
   readiness measures confirmed completeness; execution gates expose obstacles.
   There is no second percentage and no guarantee of project success.
5. In **Marketplace publication**, review readiness and unresolved information.
   Save a title if missing; review and save the business need below. Click
   **Publish challenge**, then **View in catalog**. Low readiness and blockers are
   allowed. Publication runs no AI and does not change readiness. Use **Unpublish**
   on the same page to remove catalog visibility without deleting work.
6. **Student → Explore Challenges** → open your challenge → submit a proposal.
   Select a seeded team. Example synthetic submission: idea “Compare clauses with
   the approved template”; plan “Review supplied examples, build a comparison
   demo, and review findings with the business”; timeline “Two weeks”; prototype
   `https://example.com/contract-demo`. These are student proposals, not AI output.
7. **Business → Review proposals** → **Accept** or **Reject**. Decisions are manual
   and independent; accepting one does not reject others.

## If OpenAI is unavailable

Saved drafts, answers, confirmations, and any previous analysis remain available.
Use **Retry AI** or rerun the execution test only when ready; retries are explicit
paid calls. Check that backend was started with `--env-file .env` and the local
model is `gpt-5.4-mini`; never expose the key in logs/screenshots.

Continue with the seeded catalog, readiness breakdowns, proposals, and manual
decisions without AI. A new execution result cannot be produced offline; show
the [recorded real verification](backend/REAL_STRESS_VERIFICATION.md) as a report,
not as a live result. A stored stale analysis must remain labeled stale.

## Return to baseline

`python seed.py` is repeatable and preserves demo edits. `python seed.py --reset`
replaces only seed-owned data. Reset refuses when demo tasks have interview
history or new proposals reference demo records; it does not remove newly created
operator challenges. Do not bypass that protection.

For a clean session, stop the backend and use a **new, unused database filename**.
From `backend/` with the virtual environment active (PowerShell):

```powershell
$env:DATABASE_URL = "sqlite:///./judge-demo-02.db"
python seed.py
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --env-file .env
```

On macOS/Linux replace the first line with
`export DATABASE_URL=sqlite:///./judge-demo-02.db`. Choose another unused filename
for each fresh run; existing files retain their data. This preserves the previous
session and starts with 8 challenges, 5 teams, and 9 proposals. The shell override
applies to both seed and server. To return to the default database, stop the server
and use `Remove-Item Env:DATABASE_URL` (PowerShell) or `unset DATABASE_URL` (bash).

Use a fresh browser private window for the next demo to avoid restoring old
browser-local draft/answer text. Database files and local env files are ignored.
