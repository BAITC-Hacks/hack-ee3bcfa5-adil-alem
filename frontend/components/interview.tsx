"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  api, ApiError, type Challenge, type Interview, type InterviewAnswer,
  type InterviewQuestion, type InterviewSource, type KnowledgeField,
  type KnowledgeItem, type KnowledgeStatus, type QuestionDifficulty,
} from "@/lib/api";
import { ReadinessBadge, ReadinessScore } from "./readiness";
import { ErrorState, LoadingState } from "./states";
import { ChallengeExecutionTest } from "./execution-test";
import { ChallengePublication } from "./publication";

const fieldLabels: Record<KnowledgeField, string> = {
  context: "Business context", need: "Business need", users: "Who this helps",
  data: "Available data & materials", expected_result: "Expected result",
  success_criteria: "Success criteria", constraints: "Constraints",
  contact: "Business contact", interaction_format: "Working with the business",
};
const fieldNames = Object.keys(fieldLabels) as KnowledgeField[];
const difficultyLabels: Record<QuestionDifficulty, string> = {
  QUICK: "Quick question", THINK: "A little reflection", DEEP: "Take your time", EXPERT: "May need another person",
};
const unresolved = new Set<KnowledgeStatus>(["UNKNOWN", "NEEDS_EXPERT", "NOT_APPLICABLE", "CONFLICT"]);
function knowledgeLabel(item?: KnowledgeItem) {
  if (!item) return "Open";
  if (item.status === "CONFIRMED" && item.confirmed) return "Confirmed";
  if (item.status === "UNKNOWN") return "Unknown";
  if (item.status === "NEEDS_EXPERT") return "Needs expert";
  if (item.status === "NOT_APPLICABLE") return "Not applicable";
  if (item.status === "CONFLICT") return "Conflicting information";
  return item.value ? "Provided · review needed" : "Open";
}
function loadLocal<T>(key: string): T | null {
  try { return JSON.parse(localStorage.getItem(key) || "null") as T | null; }
  catch { return null; }
}
function storeLocal(key: string, value: unknown) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* Server copies remain available if browser storage is disabled. */ }
}
const draftKey = "sana-business-draft";
type LocalDraft = { text: string; title: string; taskId?: number };

export function NewChallenge() {
  const router = useRouter();
  const [draft, setDraft] = useState<LocalDraft>({ text: "", title: "" });
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("");
  const [error, setError] = useState("");
  const lock = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    const saved = loadLocal<LocalDraft>(draftKey);
    if (saved && typeof saved.text === "string" && typeof saved.title === "string") setDraft(saved);
    setLoaded(true);
    return () => { mounted.current = false; };
  }, []);
  function change(update: Partial<LocalDraft>) {
    const next = { ...draft, ...update };
    setDraft(next); storeLocal(draftKey, next);
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (lock.current) return;
    if (!draft.text.trim()) { setError("Describe the problem in your own words before starting."); return; }
    if (draft.taskId) { router.push(`/business/challenges/${draft.taskId}/interview`); return; }
    lock.current = true; setBusy(true); setError(""); setStage("Saving your original description…");
    let taskId: number | undefined;
    try {
      const task = await api.createTask({ context: draft.text, ...(draft.title.trim() ? { title: draft.title } : {}) });
      taskId = task.id;
      const saved = { ...draft, taskId };
      setDraft(saved); storeLocal(draftKey, saved);
      setStage("Preparing your first questions… Your draft has been saved.");
      await api.startInterview(String(taskId));
    } catch (err) {
      if (!taskId) setError(err instanceof ApiError && err.status === 422 ? "Please check your description and try again." : "We couldn't confirm that your draft was saved. Your original text is kept here. Check the business workspace before retrying to avoid a duplicate.");
      // If the AI call failed, the task is already saved. Its interview page provides retry and review.
    } finally {
      if (taskId && mounted.current) router.push(`/business/challenges/${taskId}/interview`);
      else { setBusy(false); lock.current = false; }
    }
  }
  return <>
    <Link className="back-link" href="/business">← Business workspace</Link>
    <header className="detail-header interview-intro">
      <div className="eyebrow accent">A BUSINESS CHALLENGE, IN YOUR WORDS</div>
      <h1>What would you like to improve or solve?</h1>
      <p className="muted">You don&apos;t need a technical specification. Describe the problem in your own words.</p>
    </header>
    <div className="detail-layout">
      <form className="brief proposal-form new-challenge" onSubmit={submit}>
        <fieldset disabled={!loaded || busy || !!draft.taskId}>
          <label>Working title <span className="muted font-normal">(optional)</span><input name="title" value={draft.title} onChange={event => change({ title: event.target.value })} maxLength={255} /></label>
          <label>Your description<textarea name="description" rows={10} required value={draft.text} onChange={event => change({ text: event.target.value })} /></label>
        </fieldset>
        <p className="muted text-sm">Start with what you know. Uncertainty is welcome; you can leave questions open or involve another knowledgeable person.</p>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="interview-actions">
          {draft.taskId ? <Link className="button" href={`/business/challenges/${draft.taskId}/interview`}>Continue saved challenge</Link> : <button className="button" disabled={!loaded || busy} type="submit">{busy ? "Preparing interview…" : "Start interview"}</button>}
          {draft.taskId && !busy && <button type="button" className="quiet-button" onClick={() => { const next = { text: "", title: "" }; setDraft(next); storeLocal(draftKey, next); }}>Start a separate challenge</button>}
        </div>
        {stage && <p className="muted text-sm save-status" role="status">{stage}</p>}
      </form>
      <aside className="readiness-panel interview-explainer">
        <div className="eyebrow accent">FROM EXPERIENCE TO A CLEARER BRIEF</div>
        <h2>Your knowledge. A little structure.</h2>
        <ol><li>Describe the situation in your own words.</li><li>Explore a few neutral questions at a time.</li><li>Review, edit, and confirm what you know.</li></ol>
        <p className="panel-description">AI structures business knowledge. It does not create business knowledge. Your original words remain available throughout.</p>
        <div className="score-note">You can finish at any time.<br />Readiness is calculated by rules, never by AI.</div>
      </aside>
    </div>
  </>;
}

function InterviewQuestionCard({ question, taskId, busy, respond }: {
  question: InterviewQuestion; taskId: string; busy: boolean;
  respond: (answer: InterviewAnswer) => Promise<void>;
}) {
  const key = `sana-answer-${taskId}-${question.id}`;
  const [answer, setAnswer] = useState("");
  const [role, setRole] = useState("");
  const [expert, setExpert] = useState("");
  const [expertForm, setExpertForm] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const saved = loadLocal<{ answer: string; role: string; expert: string }>(key);
    if (saved) { setAnswer(saved.answer || ""); setRole(saved.role || ""); setExpert(saved.expert || ""); }
  }, [key]);
  function persist(next: { answer?: string; role?: string; expert?: string }) {
    storeLocal(key, { answer, role, expert, ...next });
  }
  function act(action: InterviewAnswer["action"]) {
    setError("");
    if (action === "answer" && !answer.trim()) { setError("Write your answer, or use one of the actions below."); return; }
    void respond({ question_id: question.id, action, ...(action === "answer" ? { answer } : {}), ...(role.trim() ? { source_role: role } : {}), ...(action === "needs_expert" && expert.trim() ? { expert } : {}) });
  }
  return <article className="interview-question" data-testid={`interview-question-${question.field}`}>
    <div className="question-meta"><span className="eyebrow accent">{fieldLabels[question.field]}</span><span className={`difficulty ${question.difficulty.toLowerCase()}`}>{difficultyLabels[question.difficulty]}</span></div>
    <h3>{question.text}</h3>
    {question.kind === "not_applicable_check" && <p className="muted text-sm">A single check before this is marked not applicable. You may confirm using “Not applicable”.</p>}
    <fieldset disabled={busy} className="question-inputs">
      <label className="sr-only" htmlFor={`answer-${question.id}`}>Your answer: {fieldLabels[question.field]}</label>
      <textarea id={`answer-${question.id}`} value={answer} rows={3} onChange={event => { setAnswer(event.target.value); persist({ answer: event.target.value }); }} />
      <details className="answer-role"><summary>Add your role (optional)</summary><label>Your role<input value={role} onChange={event => { setRole(event.target.value); persist({ role: event.target.value }); }} /></label></details>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="question-actions"><button className="button" onClick={() => act("answer")}>Answer</button><button className="quiet-button" onClick={() => act("dont_understand")}>I don&apos;t understand</button><button className="quiet-button" onClick={() => act("dont_know")}>I don&apos;t know</button><button className="quiet-button" onClick={() => setExpertForm(value => !value)}>Needs another expert</button><button className="quiet-button" onClick={() => act("not_applicable")}>Not applicable</button></div>
      {expertForm && <div className="expert-input"><label>Who could help? <span className="muted">(name or role, optional)</span><input aria-label="Expert name or role" value={expert} onChange={event => { setExpert(event.target.value); persist({ expert: event.target.value }); }} /></label><button className="button secondary" onClick={() => act("needs_expert")}>Mark needs expert</button><p className="muted text-sm">This records the information only. No invitation is sent.</p></div>}
    </fieldset>
  </article>;
}

function ReviewField({ field, task, item, sources, busy, save, confirm }: {
  field: KnowledgeField; task: Challenge; item?: KnowledgeItem; sources: InterviewSource[]; busy: boolean;
  save: (field: KnowledgeField, value: string) => Promise<void>; confirm: (field: KnowledgeField) => Promise<void>;
}) {
  const initial = item?.value ?? task[field] ?? "";
  const [value, setValue] = useState(initial);
  const reviewKey = `sana-review-${task.id}-${field}`;
  useEffect(() => {
    try {
      const saved = JSON.parse(sessionStorage.getItem(reviewKey) || "null");
      setValue(saved?.base === initial && typeof saved.value === "string" ? saved.value : initial);
    } catch { setValue(initial); }
  }, [initial, reviewKey]);
  function edit(value: string) {
    setValue(value);
    try { sessionStorage.setItem(reviewKey, JSON.stringify({ base: initial, value })); } catch { /* Optional tab-local recovery. */ }
  }
  const saved = value === (task[field] ?? "");
  const isConfirmed = task.confirmed_fields.includes(field) && saved && !unresolved.has(item?.status || "OPEN");
  const canConfirm = saved && !!value.trim() && !unresolved.has(item?.status || "OPEN") && !isConfirmed;
  const source = sources.find(source => source.id === item?.source);
  const conflictingSource = sources.find(source => source.id === item?.conflicting_source);
  return <section className="review-field" data-testid={`review-${field}`}>
    <div className="field-heading"><h3>{fieldLabels[field]}</h3><span className={`knowledge-status ${(item?.status || "OPEN").toLowerCase()}`}>{isConfirmed ? "Confirmed" : knowledgeLabel(item)}</span></div>
    <label className="sr-only" htmlFor={`review-${field}`}>Review {fieldLabels[field]}</label>
    <textarea id={`review-${field}`} rows={field === "context" ? 4 : 3} value={value} disabled={busy} onChange={event => edit(event.target.value)} placeholder="Not provided" />
    {source && <details className="source-excerpt"><summary>Original source{source.role ? ` · ${source.role}` : ""}</summary><blockquote>{source.text}</blockquote></details>}
    {conflictingSource && <details className="source-excerpt"><summary>Potentially conflicting original source{conflictingSource.role ? ` · ${conflictingSource.role}` : ""}</summary><blockquote>{conflictingSource.text}</blockquote></details>}
    {item?.expert && <p className="expert-reference">Knowledge contact: {item.expert}</p>}
    <div className="review-actions"><button className="button secondary" disabled={busy || saved} onClick={() => save(field, value)}>Save reviewed value</button><button className="button" disabled={busy || !canConfirm} onClick={() => confirm(field)}>{isConfirmed ? "Confirmed" : "Confirm field"}</button></div>
    <p className="review-hint">{unresolved.has(item?.status || "OPEN") ? "This information is unresolved and cannot earn readiness points. Save a known value if you can now provide it." : !saved ? "Review and save this value before confirming it. Saving does not award readiness points." : isConfirmed ? "Confirmed by a person. Editing this field will remove its confirmation." : "Only confirm information you have reviewed and can stand behind."}</p>
  </section>;
}

function KnowledgeMap({ task, interview }: { task: Challenge; interview: Interview | null }) {
  return <aside className="readiness-panel knowledge-panel">
    <div className="eyebrow">CHALLENGE READINESS</div>
    <ReadinessScore score={task.score} level={task.readiness_level} />
    <ReadinessBadge level={task.readiness_level} />
    <p className="panel-description">Only human-confirmed fields contribute. Readiness describes the completeness of the brief; it is not the goal of this interview.</p>
    <hr /><h2>Your knowledge map</h2>
    <div className="knowledge-list">{fieldNames.map(field => {
      const item = interview?.items.find(item => item.field === field);
      const confirmed = task.confirmed_fields.includes(field) && !unresolved.has(item?.status || "OPEN");
      return <div key={field} data-testid={`knowledge-${field}`}><a href={`#review-${field}`}>{fieldLabels[field]}</a><span className={`knowledge-status ${(item?.status || "OPEN").toLowerCase()}`}>{confirmed ? "Confirmed" : knowledgeLabel(item)}</span>{item?.value && <p>{item.value}</p>}{!item?.value && <p className="muted">{item?.status === "UNKNOWN" ? "The current contributor does not know yet." : item?.status === "NEEDS_EXPERT" ? "Another knowledgeable person is needed." : item?.status === "NOT_APPLICABLE" ? "Marked not applicable by the contributor." : "No information established yet."}</p>}{item?.expert && <p className="expert-reference">Knowledge contact: {item.expert}</p>}</div>;
    })}</div>
    <div className="score-note">AI interpretations require your review.<br />Original words remain the source of truth.</div>
  </aside>;
}

export function ChallengeInterview({ id }: { id: string }) {
  const [task, setTask] = useState<Challenge | null>(null);
  const [interview, setInterview] = useState<Interview | null>(null);
  const [loading, setLoading] = useState(true);
  const [missing, setMissing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [executionRevision, setExecutionRevision] = useState(0);
  const lock = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setMissing(false); setError("");
    Promise.all([
      api.task(id, controller.signal),
      api.interview(id, controller.signal).catch(error => { if (error instanceof ApiError && error.status === 404) return null; throw error; }),
    ]).then(([task, state]) => {
      if (!controller.signal.aborted) { setTask(task); setInterview(state); }
    }).catch(error => {
      if (!controller.signal.aborted) { setMissing(error instanceof ApiError && error.status === 404); setError("We couldn't load the interview. Your saved challenge and answers remain available when the service reconnects."); }
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [id, attempt]);
  const refresh = useCallback(async () => {
    const [task, state] = await Promise.all([api.task(id), api.interview(id).catch(error => { if (error instanceof ApiError && error.status === 404) return null; throw error; })]);
    setTask(task); setInterview(state);
  }, [id]);
  async function run(action: () => Promise<void>, success?: string) {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError(""); setNotice("");
    try { await action(); if (success) setNotice(success); }
    catch (error) { setError(error instanceof ApiError && error.status === 422 ? error.detail || "This field cannot be confirmed yet. Review the value and save any changes first." : "We couldn't confirm the latest change. Your saved draft and original answers are retained. Reload the interview to check its current state before trying again."); }
    finally { lock.current = false; setBusy(false); setExecutionRevision(value => value + 1); }
  }
  async function changeInterview(action: () => Promise<Interview>) {
    await run(async () => { setInterview(await action()); setTask(await api.task(id)); });
  }
  async function changePublication(published: boolean) {
    await run(async () => {
      try { setTask(await (published ? api.publishTask(id) : api.unpublishTask(id))); }
      catch (error) {
        if (error instanceof ApiError && error.status === 422) throw new ApiError(422, "A saved, nonblank title and business need are required to publish. Save the title here and the business need in Human review, then try again. Nothing was filled in automatically.");
        throw error;
      }
    }, published ? "Challenge published" : "Challenge unpublished. It is no longer visible in the catalog.");
  }
  if (loading) return <LoadingState />;
  if (!task) return <ErrorState notFound={missing} retry={() => setAttempt(value => value + 1)} />;
  const isFinished = interview?.status === "paused" || interview?.status === "complete";
  return <>
    <Link className="back-link" href="/business">← Business workspace</Link>
    <header className="detail-header interview-header"><div><div className="eyebrow accent">BUSINESS KNOWLEDGE · ADAPTIVE INTERVIEW</div><h1>{task.title || "Your challenge, taking shape."}</h1><p className="muted">A few questions at a time. Share what you know; leave room for what you don&apos;t.</p></div><button className="button secondary" disabled={busy || interview?.status === "paused"} onClick={() => changeInterview(() => api.finishInterview(id))}>Finish for now</button></header>
    {error && <div className="form-error" role="alert"><p>{error}</p><button className="quiet-button" disabled={busy} onClick={() => run(refresh, "Saved interview reloaded.")}>Reload saved interview</button></div>}
    {interview?.error && <div className="form-error ai-error" role="alert"><h2>The interview assistant is temporarily unavailable</h2><p>{interview.error}</p><p>Your draft and saved answers are preserved. You can review them, finish for now, or retry.</p>{!isFinished && <button className="button secondary" disabled={busy} onClick={() => changeInterview(() => api.retryInterview(id))}>Retry AI</button>}</div>}
    {busy && <p className="interview-progress" role="status"><span className="loading-dot" />Saving and preparing the next step… Your words remain in the saved interview.</p>}
    {notice && <p className="save-status" role="status">{notice}</p>}
    <ChallengeExecutionTest key={id} taskId={id} revision={executionRevision} disabled={busy} publication={blockers => <ChallengePublication task={task} interview={interview} blockers={blockers} busy={busy} publish={() => void changePublication(true)} unpublish={() => void changePublication(false)} saveTitle={title => void run(async () => { setTask(await api.updateTask(id, { title: title.trim() || null })); }, "Challenge title saved.")} />} />
    <div className="detail-layout interview-layout"><div className="interview-main">
      <section aria-labelledby="interview-questions-heading" className="interview-batch">
        <div className="section-heading"><h2 id="interview-questions-heading">{isFinished ? "Ready to review your knowledge" : "Let’s understand the challenge"}</h2><span className="muted text-sm">{interview?.status === "paused" ? "Paused" : interview?.status === "complete" ? "Current interview complete" : "Your perspective matters"}</span></div>
        {isFinished ? <div className="interview-completion"><h3>{interview?.status === "paused" ? "Saved. You can return whenever you’re ready." : "There’s enough to review for now."}</h3><p>{interview?.completion_reason || "Review what is known and keep the remaining gaps visible. Every field does not need an answer."}</p><p>There is no target readiness score. Unresolved information can stay open.</p>{interview?.status === "paused" ? <button className="button secondary" disabled={busy} onClick={() => changeInterview(() => api.startInterview(id))}>Resume interview</button> : <Link className="button secondary" href="/business">Business workspace</Link>}</div>
          : interview?.questions.length ? <div>{interview.questions.map(question => <InterviewQuestionCard key={question.id} taskId={id} question={question} busy={busy || !!interview.error} respond={answer => changeInterview(() => api.respondInterview(id, answer))} />)}</div>
          : !interview ? <div className="interview-completion"><h3>Your original draft is saved.</h3><p>Start the interview to organize what you have provided and explore unanswered questions.</p><button className="button" disabled={busy} onClick={() => changeInterview(() => api.startInterview(id))}>Start interview</button></div>
          : !interview.error ? <div className="interview-completion"><p>No questions are currently available. You can review the knowledge below or finish for now.</p></div> : null}
      </section>
      <section className="brief interview-review" aria-labelledby="review-heading"><div className="eyebrow accent">HUMAN REVIEW</div><h2 id="review-heading">Review before you confirm</h2><p className="muted text-sm">Compare the structured values with your original words. Edit and save each value, then confirm it only if it is accurate. AI never confirms for you.</p>
        {fieldNames.map(field => <ReviewField key={field} field={field} task={task} item={interview?.items.find(item => item.field === field)} sources={interview?.sources || []} busy={busy} save={(field, value) => run(async () => { setTask(await api.updateTask(id, { [field]: value.trim() ? value : null })); await refresh(); }, "Reviewed value saved. Confirmation is a separate step.")} confirm={field => run(async () => { setTask(await api.confirmTask(id, [field])); await refresh(); }, "Field confirmed. Readiness was recalculated by the existing rules.")} />)}
      </section>
      <section className="brief original-sources"><h2>Original words and sources</h2><p className="muted text-sm">The original contributions stay available. Structured interpretations do not replace them.</p>{interview?.sources.length ? interview.sources.map(source => <details key={source.id}><summary>{source.kind.replaceAll("_", " ")}{source.role ? ` · ${source.role}` : " · Contributor"}</summary><blockquote>{source.text}</blockquote></details>) : <blockquote>{task.context || "No source text recorded yet."}</blockquote>}</section>
    </div><KnowledgeMap task={task} interview={interview} /></div>
  </>;
}
