# Step 8 — execution test implementation and verification

Date: 2026-09-23. **PASS for the tested hackathon scenario after targeted
corrections.** Implementation, mocked regressions, and four explicitly authorized
real calls are complete. The fourth response passed both application validation
and independent semantic review. The first two responses were safely rejected;
the third exposed a gate-classification defect described below. No further paid
requests were made.

## Architecture and stored data

The existing application architecture is retained. `ai_interviewer.generate_structured`
is the shared OpenAI SDK boundary and the single location for model configuration.
Both AI features default to `gpt-5.4-mini`, honor `OPENAI_MODEL`, use strict
Pydantic structured outputs, disable provider retries, and set `store=false`.

The dedicated `StressAIResult` contains task-specific execution requirements,
their target knowledge fields, existing basis source IDs, exact evidence quotes,
and evidence assessments. It has no global executability judgment, score,
confirmation, expert-generation, or team-selection properties.

The server validates the plan and derives PASS/BLOCKED/NOT_APPLICABLE for each
requirement, then aggregates the five gates. Requirements adapt to the challenge;
a dataset is not a universal requirement. AI interpretation is still necessary
to determine relevance and semantic sufficiency; exact quote matching alone
cannot prove that an interpretation is correct.

One additive table, `task_stress_tests`, holds `task_id` (primary/foreign key),
`input_fingerprint`, JSON `result`, and `created_at`. The existing startup
`create_all` creates it without modifying existing Task or interview schemas.
Each result includes its source snapshot. A fingerprint of relevant Task and
Knowledge Map input and the analysis version determines staleness, including edits
made during generation. Publication alone does not make an analysis stale. No
automatic AI reruns occur.

## API and frontend

- `POST /api/tasks/{id}/stress-test`: explicitly run one analysis; save only a
  validated result. Provider errors preserve the previous result.
- `GET /api/tasks/{id}/stress-test`: retrieve the latest result and freshness
  without any provider call.

Both return `{task_id, result, stale, error}`. Unknown tasks return 404. A task
with no prior test returns `result=null`. Recoverable provider/validation errors
are returned in the response envelope without credentials or provider payloads.

The business interview/review page contains **Run execution test**, five expandable
gates, `X/5 gates passed`, blocker count, required-information questions, explicit
knowledge statuses, known experts, and source snapshots. It supports loading,
staleness, reruns, and persistent error/retry messages. Edits and tab focus only
refresh the saved result with GET. The existing visual design is preserved.

Readiness remains deterministic completeness of human-confirmed information.
The execution test is a diagnostic of whether students have the information to
begin. Neither predicts success or selects a team. Blockers do not prevent
publication, change readiness, confirm fields, alter the Task, or affect proposals.

## Mocked tests and fixes

Added 27 backend stress tests covering complete challenges, unknown ML access,
genuinely unnecessary datasets, missing validation/deliverables, known experts,
conflicts, unconfirmed information, preservation of business state, publication,
persistence, staleness, mid-request edits, malformed JSON, and provider outages.
Additional checks reject invented references, quotes, experts, or extra scores;
unrelated source authority and missing gate coverage are also exercised.

Seven schema tests verify current source enums, confirmation authority, empty
evidence, explicit N/A, base-schema compatibility, unmodified input, and no provider
call for an empty description. Three adapter tests verify shared model selection, the dedicated schema,
disabled retries/storage, and safe missing-key behavior. Four browser tests
cover all ten requested UI scenarios, using real local API/database routes and
mocking both AI providers before starting the test server.

Review identified and fixed:

- Cross-field NOT_APPLICABLE evidence initially accepted any confirmed field.
  It now requires confirmed scope information (context, need, expected result,
  constraints) or the requirement's own field. A contact email cannot establish
  that a dataset is unnecessary.
- Mixed valid/unrelated evidence could otherwise pass through an `any` check.
  All asserted authoritative evidence must satisfy the relevant authority check.
- A follow-up GET could erase a POST error from the UI. Run errors now persist
  until an explicit retry, even across focus-triggered reads.
- Refreshing an existing result now visibly indicates that freshness is being
  checked; a failed GET explicitly marks freshness as unverified.

| Verification | Result |
| --- | --- |
| Full backend unit/API suite after final prompt/version correction | **89/89 passed** |
| Live HTTP smoke checks | **206/206 passed** |
| Full browser suite | **18/18 passed** |
| Next.js production build | **Passed** |
| TypeScript `tsc --noEmit` | **Passed** |

Total: **107 automated test cases and 206 HTTP smoke checks**. Regression child
processes used an empty API key and a sentinel model. The frontend was built for
the isolated local test backend. Windows sandbox restrictions initially prevented
test subprocess cleanup; clean final runs with approved process termination
permissions exited successfully. No regression test made a real OpenAI call.

## Real golden scenario

`verify_real_stress.py` copies the existing Step 7.5 database into ignored
`.stress-verification/`, preserving the original synthetic sources and statuses.
The original Step 7.5 database and development data remain unchanged.

The exact initial context remains:

```text
Our employees spend too much time reviewing contracts.
We want to automate this process.
```

The existing manually supplied answer is:

```text
We need to identify clauses that differ from our approved contract template.
```

`users` remains UNKNOWN. `data` remains NEEDS_EXPERT with user-provided
`expert="IT department"`; access is not assumed. Context and need remain OPEN and
unconfirmed. **All four calls used the same unchanged business information.** The
call budget was used to investigate observed defects; the runner's optional
`confirm-known` action was not used. Human-confirmed PASS and NOT_APPLICABLE cases
were verified with mocked tests, not with these real requests.

The first invocation attempt was blocked by automatic approval review. Rechecking
the latest Step 8 attachment and resubmitting the same action was also blocked:
the reviewer required authorization directly in a user message, rather than the
attached instruction, because Step 7.5 had previously forbidden Stress Test work.
The user subsequently explicitly authorized Step 8 and two real requests, then
separately authorized a third and a fourth, final request to verify corrections.
All ran through the normal approved path. No alternative network path was used.
The permission-review denials did not start the SDK or consume tokens.

## Real calls, observed failures, and corrections

All four requests explicitly used `gpt-5.4-mini`; every provider response reported
`gpt-5.4-mini-2026-03-17` through HTTPS `api.openai.com`. SDK retries were disabled,
`store=false`, and no fallback model was used.

| Call | Input | Output | Total | Application result |
| --- | ---: | ---: | ---: | --- |
| Initial golden analysis | 2,914 | 582 | 3,496 | Rejected: fabricated/misattributed evidence |
| Retry after prompt/schema descriptions | 3,310 | 455 | 3,765 | Rejected: requirements with only empty basis sources |
| Request-specific source schema | 3,272 | 520 | 3,792 | Sources valid; semantic review found START/ACCESS misclassification |
| Explicit gate-boundary correction | 3,408 | 463 | 3,871 | Accepted; independent semantic review passed |
| **Total** | **12,904** | **2,020** | **14,924** | **4 completed calls** |

Reported cached and reasoning tokens were zero. There were no additional SDK
requests for regression testing or final offline checks.

The first output quoted literal `null` for absent fields, attributed an interview
answer to an empty Task slot, quoted expert-action metadata as a knowledge value,
and proposed SUPPORTED for unconfirmed fields. The validator rejected the entire
plan. No Task, confirmation, readiness, or stored business knowledge changed.

The first correction reinforced source rules in the prompt and Pydantic field
descriptions. It required empty evidence for MISSING, separate Task/Knowledge Map
IDs, and actual source text rather than null/status metadata. Two mocked regression
tests reproduce the observed source errors. The second real response removed the
fabricated null/action quotes but still referenced empty knowledge slots as the
only basis for some requirements and proposed SUPPORTED for OPEN context. It was
again rejected safely. These two calls prove that prompt instructions alone were
insufficient for this model/scenario.

A further correction constrains model source choices through a request-specific
Pydantic schema derived from `StressAIResult`. Basis references are an enum of
nonempty, non-action business sources. Evidence references are limited to current
confirmed sources. For this unchanged golden scenario, the schema permits only
five valid basis source IDs, empty evidence arrays, and MISSING assessments,
because none of its fields are human-confirmed. Explicit user N/A remains
representable in requests that contain such a classification.

This does not rewrite model references, manufacture evidence, or relax the
server's source validation. The third response passed these checks, but critical
review found that it assigned contract-material availability to START and
identification of users to ACCESS. Identifying an audience is not the same as
being able to access a required resource. That result was not accepted as proof
of correct model behavior merely because its JSON and references were valid.

The smallest additional correction clarified those conceptual gate boundaries
in the prompt: START concerns scope clarity sufficient to identify an initial
activity; ACCESS concerns actual resources/materials/access. Requirements remain
adaptive; there is no fixed field-to-gate checklist. Increasing the input's
`analysis_version` marked the saved third result stale without editing its text.
The fourth explicitly authorized call then replaced it with the final result.

All **4/4** real responses parsed against their structured-output schemas.
Application validation accepted **2/4**. Of those, the third required a semantic
correction; the fourth passed independent semantic review. Structured JSON and
valid references alone do not prove that gate assignment or interpretation is
correct.

## Actual final output

Saved at `2026-09-23T11:27:12.104314Z`:
**0/5 gates passed, 7 blocked requirements, stale=false, error=null.**

| Gate | Actual model requirement | Knowledge status | Result |
| --- | --- | --- | --- |
| UNDERSTAND | Understand the business problem and objective. | OPEN; context unconfirmed | BLOCKED |
| UNDERSTAND | Understand the specific review target. | OPEN; need unconfirmed | BLOCKED |
| START | Have enough scope clarity to identify a first action. | OPEN; need unconfirmed | BLOCKED |
| ACCESS | Know what contract materials or inputs are available. | NEEDS_EXPERT; IT department | BLOCKED |
| VALIDATE | Understand how the result will be judged successful. | OPEN; success criteria missing | BLOCKED |
| DELIVER | Understand the expected deliverable. | OPEN; expected result missing | BLOCKED |
| DELIVER | Understand any stated constraints on the deliverable. | OPEN; constraints missing | BLOCKED |

The count is seven blocked requirements, not seven independent missing facts:
unconfirmed `need` affects both UNDERSTAND and START. No required field was
silently confirmed. The model did not select UNKNOWN `users` as a separate
execution requirement in the final run; its stored UNKNOWN status remained intact.

The seven actual required-information questions, in the same order:

1. What is the business problem and what outcome is wanted?
2. What must the automation identify in the contracts?
3. What exactly is the contract-review automation supposed to focus on?
4. What contract documents, templates, or related inputs are available for this work?
5. How will the business determine that the automation is working well?
6. What output should the solution produce for the business?
7. Are there any constraints on how the solution should operate or be delivered?

The mention of a template is grounded in the existing manually supplied answer.
It does not claim that documents or templates are available. No technical
approach, success target, deadline, budget, security rule, named person, contact,
or expert availability was invented. The question about constraints asks whether
they exist; it does not impose a particular restriction.

The final ACCESS blocker, exactly as returned by the API:

```json
{
  "gate": "ACCESS",
  "field": "data",
  "requirement": "Know what contract materials or inputs are available.",
  "status": "BLOCKED",
  "reason": "The business marked this information as needing another expert. It remains unresolved.",
  "knowledge_status": "NEEDS_EXPERT",
  "source_refs": [
    "knowledge:context",
    "knowledge:need",
    "task:data",
    "knowledge:data",
    "095fb8f5424f405d90a4c403e99cd4fd"
  ],
  "required_information": "What contract documents, templates, or related inputs are available for this work?",
  "expert_if_known": "IT department",
  "evidence": []
}
```

`knowledge:context` and `knowledge:need` establish why contract materials matter.
The empty Task data field, current Knowledge Map status, and original user action
`needs_expert: IT department` establish what is unresolved and who was named.
An empty `evidence` array correctly indicates no confirmed evidence of access;
the original source references still explain the blocker.

Readiness stayed **0/100, draft**, with `confirmed_fields=[]`. It is independent
of the execution gate count. The Stress Test did not compute or change it.

## Final integrity checks and limits

An offline GET after the fourth run returned the same persisted result with
`stale=false`, without another model call or transcript modification. Every
returned source reference exists in the saved source snapshot. SQLite comparison
confirmed all Task, interview, team, and proposal rows in the isolated database
still match the original Step 7.5 database. No business data changed.

The local `.env`, frontend `.env.local`, and verification database/transcript
are ignored and untracked. A scan of 82 Git-visible/artifact files found no
occurrence of the configured API key. The transcript contains synthetic source
data, outputs, and usage; it contains no credentials or request headers.

**Final verdict: PASS for the tested hackathon scenario.** The real final run
demonstrates source-grounded blockers, unknown access, and preservation of the
user-provided expert. Confirmed PASS, NOT_APPLICABLE, outages, stale results,
publication with blockers, and frontend retry behavior are covered by mocked
regressions. This four-response run does not establish reliability across all
possible business scenarios; semantic interpretation still needs review. No
second score, automatic confirmation, technical solution generator, or later-step
feature was introduced.
