# Step 7.5 — real OpenAI verification

Run date: 2026-09-23. Scope: the existing adaptive interview only.
The manual runner used the real OpenAI SDK through the actual FastAPI interview
routes with an isolated SQLite database. No production/demo records were changed.

## Model, calls, and usage

Every request explicitly sent `model=gpt-5.4-mini`. Every provider response
reported `gpt-5.4-mini-2026-03-17`. No model fallback was used. Requests used
`store=false`, `max_retries=0`, and the existing Pydantic structured-output schema.
SDK endpoint inspection confirmed HTTPS `api.openai.com`, with no custom base URL.

There were **5 completed real API calls**, including the failed semantic result
and its explicit retry. A separate initial SDK attempt failed with
`APIConnectionError` in the network sandbox, without an HTTP response or usage;
it is not counted as a completed provider call. Total SDK attempts: **6**.

| Real call | Mode / purpose | Input tokens | Output tokens | Result |
| --- | --- | ---: | ---: | --- |
| 1 | Golden draft / batch | 1,459 | 137 | Accepted |
| 2 | Concrete answer / extract | 1,513 | 116 | Accepted |
| 3 | Original rephrase | 1,684 | 145 | Rejected by grounding/mode validation |
| 4 | Rephrase after targeted correction | 1,777 | 45 | Accepted |
| 5 | Next batch after expert action | 1,734 | 187 | Accepted |
| **Total** | | **8,167** | **630** | **8,797 tokens** |

Reported cached tokens and reasoning tokens were both zero. No additional paid
requests were made for regression testing. The API key was never printed or
included in artifacts. `.env` and the local transcript directory are ignored and
not tracked by Git.

## Golden extraction and actual questions

The task was created with exactly this context and no other business fields:

```text
Our employees spend too much time reviewing contracts.
We want to automate this process.
```

The model extracted only `context`, preserving that complete text verbatim and
citing draft source `7bbea5dc765f461f8ada329e8637e206`. All other knowledge values
remained null. The general wish for automation stayed inside the context;
the model asked for the specific need rather than inventing it.

Initial batch, verbatim:

1. **need / THINK:** “What exactly should be automated in the contract review process?”
2. **users / QUICK:** “Who will use this automation?”
3. **data / THINK:** “What contract-related information will the automation need to review?”

These questions contain no answer menus, technical recommendations, invented
departments, datasets, contract counts, APIs, technologies, deadlines, success
targets, security restrictions, budget, or available experts. They follow the
user's stated wish for automation without claiming that a solution already exists.
Minor quality observation: the initial THINK question precedes QUICK despite the
prompt's preference for QUICK first. All three remain short and accessible.

## Special actions and provenance

**A — Concrete answer.** The verifier manually supplied this synthetic fact:

```text
We need to identify clauses that differ from our approved contract template.
```

The original answer is saved unchanged as source
`172915e24cc742aca233c5975234c2c8`, kind `answer`. The extracted `need` is the same
full string and cites that source. The template was introduced by this explicit
test answer, never inferred from the golden draft. The field remains `OPEN`,
`confirmed=false`; it is not silently copied into the confirmed task card.

**B — “I don't know”.** The existing `dont_know` action was applied to `users`.
It produced `UNKNOWN`, a null value, and its own action source
`95431ba6637e4803b6a51e2a9df395e1`. It required no model call while another question
was pending. Subsequent real calls retained UNKNOWN, invented no user identity,
and did not ask the users question again.

**C — “I don't understand”.** The existing `dont_understand` action targeted
the pending `data` question. The original real response was defective: it repeated
the original question and emitted forbidden extractions with extra quote
characters and an escaped newline. The existing validator rejected the entire
response; original sources, values, and the pending question were preserved.

After the targeted correction, the actual question became:

> What contract information does the automation need to check?

This asks for the same contract information using simpler words ("review" becomes
"check", "contract-related" becomes "contract"). The field is still `data`, no
answer or example is supplied, and the extraction array is empty. The action
source `a7f49ed76f47446b81d69a586c705b37` survives the retry without duplication.

**D — “Needs another expert”.** The `needs_expert` action supplied exactly
`IT department` for `data`. The stored item has `status=NEEDS_EXPERT`,
`expert="IT department"`, `value=null`, and `confirmed=false`. Its provenance
points to action source `095fb8f5424f405d90a4c403e99cd4fd` with text
`needs_expert: IT department`. The model invented no person, contact details,
expertise, data access, or availability.

The next adaptive batch, verbatim:

1. **expected_result / QUICK:** “What should the automation produce at the end?”
2. **success_criteria / QUICK:** “How will you know the process is working well?”
3. **constraints / QUICK:** “Are there any limits or rules the solution has to follow?”

It moves to three remaining gaps, without repeating the answered need, UNKNOWN
users, or NEEDS_EXPERT data fields. Unanswered fields stay null and OPEN. All
stored non-null knowledge values were checked against their referenced original
sources. No auto-confirmation occurred. The task's score stayed **0**, readiness
stayed **draft**, and `confirmed_fields` stayed empty throughout. Score and
readiness data were absent from model input; no output judged or optimized them.

## Corrections and reliability

Only the observed rephrase issue required application changes:

- Scoped the general extraction instruction to batch/extract modes and added a
  short, explicit rephrase-only instruction: empty extractions, same field and
  meaning, different simpler wording, no answers/examples/new assumptions.
- Added rejection of unchanged rephrases after case/whitespace normalization.
  This strengthens validation; source-grounding rules were not relaxed.
- Added a mocked regression for rejection and safe retry of an unchanged question.
  Updated the existing not-applicable rephrase test's mock to actually simplify
  its question, matching the intended behavior.

All **5/5** real responses parsed successfully against `InterviewAIResult`.
Application-level semantic/provenance validation accepted **4/5**; the rejected
response was retained only in the local audit transcript, not in knowledge state.
The corrected rephrase passed **1/1** real retry, and the following adaptive batch
also passed. Structured JSON alone is therefore insufficient evidence of quality.
No fabricated business facts, leading answer suggestions, technical solutions,
or readiness judgments were found in accepted outputs. The raw rejected rephrase
did contain the provenance-formatting error described above.

## Regression and verdict

| Check | Result |
| --- | --- |
| Full backend unit/API/adapter/scoring/seed suite | **52/52 passed** |
| Live local API smoke suite | **206/206 HTTP checks passed** |
| Frontend Playwright (catalog, proposals, interview) | **14/14 passed** |
| Next.js production build | **Passed** |
| TypeScript `tsc --noEmit` | **Passed** |

Total: **66 automated test cases and 206 HTTP smoke checks**, all passing.
The first unit run exposed a mock returning unchanged wording; the fixture was
corrected and the full suite rerun. Windows sandbox process-cleanup restrictions
required a fresh smoke/browser run with permission to terminate their own child
processes; the final runs exited successfully and cleaned up their test servers.

Regression child processes had an empty `OPENAI_API_KEY` and sentinel model
`regression-must-not-call-openai`. Provider/SDK calls remain mocked where designed.
The frontend was rebuilt with `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` and tested
against the isolated mocked backend, with existing-server reuse disabled.

**Final verdict: PASS for the tested hackathon demo scenario after the targeted
rephrase correction.** This bounded five-response run establishes observed
behavior, not a guarantee that every future model response is semantically valid.
Keep the existing validation, human confirmation, and recoverable retry behavior.
No new product features, scoring logic, or frontend behavior were introduced.
