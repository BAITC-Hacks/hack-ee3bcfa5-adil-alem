# Steps 9–9.1 — submission audit

Date: 2026-09-23. **SAFE TO PUSH the audited, non-ignored files below.**
No commit or push was performed. This is a local secret/ignore audit, not a
production security certification or a dependency vulnerability assessment.

## Step 9 documentation changes

- Rewrote root README: product, principles, architecture, stack, cross-platform
  setup, seeded demo, complete verification path, limitations, and test commands.
- Added DEMO.md: short operator flow, provider recovery, and non-destructive
  baseline reset using a new SQLite filename.
- Added root .gitignore: local env variants, SQLite files/sidecars, virtualenv,
  dependencies, build outputs, test artifacts, and private verification folders.
  Safe .env.example files remain visible.
- Corrected backend README: seed reset also refuses to remove interview history.
- Added this audit and exact commit manifest. No product or AI behavior changed.

Step 9.1 removes the publication UI limitation: the complete golden demo now runs
through the frontend. Reset still does not erase new operator challenges.
For a clean-clone run, no local transcript, database, absolute workstation path,
or private key is required in the repository. Live AI needs the operator's own
backend key; all regression suites run with mocked AI.

## Step 9.1 publication UI

Added manual Publish challenge / Published / Unpublish controls to the existing
business interview/review page, with View in catalog after success. The panel
shows readiness, a current verified blocker count when available, and known
unresolved information. Stale counts are not presented as current. A missing
title can be saved explicitly; missing business need is edited in Human review.
The existing endpoints enforce publication rules. No AI, scoring, database,
Stress Test evaluation, or design-system behavior changed.

Files changed in Step 9.1: README.md, DEMO.md, SUBMISSION_AUDIT.md,
frontend/README.md, frontend/lib/api.ts, frontend/components/interview.tsx,
frontend/components/execution-test.tsx; new frontend/components/publication.tsx
and frontend/tests/zzz-publication.spec.ts.

Three new browser tests cover the complete UI journey through interview,
confirmation, stress test, publication, catalog, proposal and manual decision;
zero-readiness publication; missing-field errors and manual correction;
unpublishing; stale summaries; and retry after publication failure. Assertions
verify unchanged readiness, confirmations and saved stress results, and no AI
POSTs caused by publication. Initial new-test failures were ambiguous selectors;
these were corrected, and all tests passed on the final full run.

## Verification after Step 9.1

| Check | Result |
| --- | --- |
| Backend unittest/API suite | 89/89 passed |
| Live Uvicorn HTTP smoke checks | 206/206 passed |
| Playwright browser suite | 21/21 passed |
| Next.js production build | Passed |
| TypeScript | Passed |

Total: **110 test cases and 206 HTTP checks**. No real OpenAI calls.
Browser and smoke tests used isolated databases and cleaned up their servers.
Package-lock dependency declarations match package.json. Local links in README
and DEMO were checked. Windows commands were used in this verification; the
documented macOS/Linux equivalents were reviewed, not executed on those systems.

## Secret and Git checks

- Git-visible contents checked for the configured key and common OpenAI, GitHub,
  AWS access-key, and private-key patterns; no matches.
- Step 9.1 audit rechecked all 84 Git-visible files, including the two new files.
- Available local history/reflog objects checked: 1 commit and 83 blob objects;
  no matches. This does not establish the state of remote-only history.
- 14 ignore probes passed, including env variants, databases, virtualenv,
  node_modules, .next, and both real-model verification folders.
- Backend .env.example has an empty API key; frontend .env.example contains only
  the public API origin. Both templates are intentionally included.
- Local env and real verification data are not tracked.

At audit time, README.md was the only tracked file and was modified. Backend,
frontend, and the new root files were untracked. Nothing was staged by this step.
Review the staged diff before committing; rerun a secret check if files change.

## Exact files recommended for commit

This manifest includes all 84 currently intended files, including this report.
Use normal Git staging, never force-add ignored files:

```bash
git add -- README.md DEMO.md SUBMISSION_AUDIT.md .gitignore backend frontend
git diff --cached --stat
git diff --cached --check
```

```text
.gitignore
DEMO.md
README.md
SUBMISSION_AUDIT.md
backend/.env.example
backend/.gitignore
backend/README.md
backend/REAL_OPENAI_VERIFICATION.md
backend/REAL_STRESS_VERIFICATION.md
backend/app/__init__.py
backend/app/database.py
backend/app/interview_schemas.py
backend/app/main.py
backend/app/models.py
backend/app/routers/__init__.py
backend/app/routers/catalog.py
backend/app/routers/interview.py
backend/app/routers/proposals.py
backend/app/routers/stress_test.py
backend/app/routers/tasks.py
backend/app/routers/teams.py
backend/app/schemas.py
backend/app/services/__init__.py
backend/app/services/ai_interviewer.py
backend/app/services/ai_stress_test.py
backend/app/services/interview.py
backend/app/services/scoring.py
backend/app/services/stress_test.py
backend/app/stress_schemas.py
backend/demo_data.py
backend/requirements.txt
backend/seed.py
backend/smoke_test.py
backend/test_interview.py
backend/test_openai_boundary.py
backend/test_scoring.py
backend/test_seed.py
backend/test_stress_schema.py
backend/test_stress_test.py
backend/verify_real_openai.py
backend/verify_real_stress.py
backend/workflow_checks.py
frontend/.env.example
frontend/.gitignore
frontend/README.md
frontend/app/business/challenges/[id]/interview/page.tsx
frontend/app/business/challenges/[id]/proposals/page.tsx
frontend/app/business/new/page.tsx
frontend/app/business/page.tsx
frontend/app/challenges/[id]/page.tsx
frontend/app/challenges/[id]/propose/page.tsx
frontend/app/challenges/page.tsx
frontend/app/globals.css
frontend/app/layout.tsx
frontend/app/not-found.tsx
frontend/app/page.tsx
frontend/components/business.tsx
frontend/components/catalog.tsx
frontend/components/challenge-card.tsx
frontend/components/challenge-detail.tsx
frontend/components/execution-test.tsx
frontend/components/interview.tsx
frontend/components/navigation.tsx
frontend/components/proposal-form.tsx
frontend/components/publication.tsx
frontend/components/readiness.tsx
frontend/components/states.tsx
frontend/components/use-resource.ts
frontend/lib/api.ts
frontend/next-env.d.ts
frontend/next.config.ts
frontend/package-lock.json
frontend/package.json
frontend/playwright.config.ts
frontend/postcss.config.mjs
frontend/tests/interview_fixture.py
frontend/tests/marketplace.spec.ts
frontend/tests/proposals.spec.ts
frontend/tests/serve_backend.py
frontend/tests/stress_fixture.py
frontend/tests/z-interview.spec.ts
frontend/tests/zz-execution.spec.ts
frontend/tests/zzz-publication.spec.ts
frontend/tsconfig.json
```

## Never commit

Local .env / .env.local / other env variants (except safe examples), API keys,
SQLite databases and sidecars, .venv, node_modules, .next, __pycache__,
*.tsbuildinfo, test-results, playwright-report, logs, and
backend/.openai-verification/ or backend/.stress-verification/.

The public REAL_OPENAI_VERIFICATION.md and REAL_STRESS_VERIFICATION.md reports
contain reviewed synthetic results and are included. Their private raw transcript
directories and databases remain excluded.
