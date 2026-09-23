"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  api, ApiError, type ExecutionRequirement, type ExecutionSource,
  type ExecutionStatus, type ExecutionTest,
} from "@/lib/api";

const statusLabel: Record<ExecutionStatus, string> = {
  PASS: "PASS", BLOCKED: "BLOCKED", NOT_APPLICABLE: "NOT APPLICABLE",
};
function readable(value: string) {
  return value.replaceAll("_", " ");
}

function Requirement({ requirement, sources }: {
  requirement: ExecutionRequirement; sources: ExecutionSource[];
}) {
  return <article className="execution-requirement">
    <div className="execution-requirement-heading"><h4>{requirement.requirement}</h4><span className={`execution-status ${requirement.status.toLowerCase()}`}>{statusLabel[requirement.status]}</span></div>
    {requirement.status === "BLOCKED" && <p className="execution-stop">Student execution may stop here.</p>}
    <dl>
      <div><dt>Reason</dt><dd>{requirement.reason}</dd></div>
      {requirement.required_information && <div><dt>Required information</dt><dd>{requirement.required_information}</dd></div>}
      <div><dt>Knowledge status</dt><dd>{readable(requirement.knowledge_status)}</dd></div>
      {requirement.expert_if_known && <div><dt>Knowledge owner</dt><dd>{requirement.expert_if_known}</dd></div>}
    </dl>
    {!!requirement.source_refs.length && <details className="execution-sources">
      <summary>Show source information ({requirement.source_refs.length})</summary>
      <p className="muted text-sm">Saved with this test. Source wording and knowledge status are preserved.</p>
      {requirement.source_refs.map(ref => {
        const source = sources.find(source => source.id === ref);
        return <div className="execution-source" key={ref}>
          <div className="execution-source-meta">{source?.field ? readable(source.field) : "Original business source"}{source?.role ? ` · ${source.role}` : ""}</div>
          <code>{ref}</code>
          {source?.knowledge_status && <p className="muted text-sm">{readable(source.knowledge_status)}{source.confirmed ? " · Human-confirmed" : " · Not confirmed"}</p>}
          <blockquote>{source?.text ?? "No business value was provided in this source."}</blockquote>
          {requirement.evidence.filter(evidence => evidence.source_ref === ref).map((evidence, index) => <p className="execution-evidence" key={index}>Cited passage: <q>{evidence.quote}</q></p>)}
        </div>;
      })}
    </details>}
  </article>;
}

export function ChallengeExecutionTest({ taskId, revision, disabled, publication }: {
  taskId: string; revision: number; disabled: boolean;
  publication?: (currentBlockers: number | null) => ReactNode;
}) {
  const [view, setView] = useState<ExecutionTest | null>(null);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [running, setRunning] = useState(false);
  const [readError, setReadError] = useState("");
  const [runError, setRunError] = useState("");
  const sequence = useRef(0);
  const runLock = useRef(false);
  const activeRead = useRef<AbortController | null>(null);
  const mounted = useRef(true);

  const refresh = useCallback(async () => {
    if (runLock.current) return;
    activeRead.current?.abort();
    const controller = new AbortController();
    activeRead.current = controller;
    const request = ++sequence.current;
    setChecking(true);
    try {
      const saved = await api.stressTest(taskId, controller.signal);
      if (mounted.current && request === sequence.current) { setView(saved); setReadError(""); }
    } catch {
      if (mounted.current && !controller.signal.aborted && request === sequence.current) setReadError("We couldn't check the saved execution test. Its freshness is not verified. Retry loading when the service reconnects.");
    } finally {
      if (mounted.current && request === sequence.current) { setLoading(false); setChecking(false); }
    }
  }, [taskId]);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; sequence.current++; activeRead.current?.abort(); };
  }, []);
  useEffect(() => { if (!running) void refresh(); }, [refresh, revision, running]);
  useEffect(() => {
    const onFocus = () => { if (document.visibilityState === "visible") void refresh(); };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onFocus);
    return () => { window.removeEventListener("focus", onFocus); document.removeEventListener("visibilitychange", onFocus); };
  }, [refresh]);

  async function run() {
    if (runLock.current) return;
    runLock.current = true;
    activeRead.current?.abort();
    const request = ++sequence.current;
    setRunning(true); setRunError("");
    try {
      const result = await api.runStressTest(taskId);
      if (mounted.current && request === sequence.current) { setView(result); setReadError(""); setRunError(result.error || ""); }
    } catch (error) {
      if (mounted.current && request === sequence.current) setRunError(error instanceof ApiError && error.detail ? error.detail : "We couldn't confirm a new execution test. Any previous result is kept below. Retry explicitly when the service reconnects.");
    } finally {
      runLock.current = false;
      if (mounted.current && request === sequence.current) { setRunning(false); setLoading(false); }
    }
  }

  const result = view?.result;
  const error = runError || view?.error;
  return <><section className="execution-panel" aria-labelledby="execution-heading" data-testid="execution-test">
    <div className="execution-header"><div><div className="eyebrow accent">EXECUTION TEST</div><h2 id="execution-heading">Could a student team begin?</h2><p>Understand what execution needs, where work could stop, and which information is still needed.</p></div><button className="button" onClick={() => void run()} disabled={disabled || loading || running}>{running ? "Running execution test…" : error ? "Retry execution test" : result ? "Run execution test again" : "Run execution test"}</button></div>
    <p className="execution-distinction">Readiness measures completeness of human-confirmed information. This test examines execution requirements. Neither predicts project success or selects a team.</p>
    {loading && <p className="save-status" role="status">Loading the saved execution test…</p>}
    {result && checking && <p className="save-status" role="status">Checking saved result freshness…</p>}
    {running && <p className="interview-progress" role="status"><span className="loading-dot" />Checking execution requirements against the current knowledge. Previous results remain visible until this completes.</p>}
    {readError && <div className="form-error" role="alert"><p>{readError}</p><button className="quiet-button" disabled={running} onClick={() => void refresh()}>Reload saved execution test</button></div>}
    {error && <div className="form-error" role="alert"><p>{error}</p><p>No new analysis has been accepted. Any previous result remains below.</p></div>}
    {view?.stale && result && <div className="execution-stale" role="status"><strong>Previous result · needs an update</strong><p>Challenge information changed since this test. Run again for an updated execution analysis.</p></div>}
    {result ? <>
      <div className="execution-summary"><strong>{result.gates_passed}/5 gates passed</strong><span>{result.blocker_count} {result.blocker_count === 1 ? "blocker" : "blockers"}</span><time dateTime={result.created_at}>Last test: {new Date(result.created_at).toLocaleString()}</time></div>
      <ol className="execution-gates">{result.gates.map((gate, index) => <li key={gate.gate}>
        <details className={`execution-gate ${gate.status.toLowerCase()}`} data-testid={`execution-gate-${gate.gate}`}>
          <summary><span className="execution-gate-number">{String(index + 1).padStart(2, "0")}</span><h3>{gate.gate}</h3><span className={`execution-status ${gate.status.toLowerCase()}`}>{statusLabel[gate.status]}</span><span className="execution-expand" aria-hidden="true">+</span></summary>
          <div className="execution-gate-body">{gate.requirements.map((requirement, index) => <Requirement key={index} requirement={requirement} sources={result.sources} />)}</div>
        </details>
      </li>)}</ol>
      <p className="execution-footnote">A diagnostic of the saved information. Blockers do not prevent publication, change readiness, confirm fields, or affect proposal decisions.</p>
    </> : !loading && <p className="execution-empty">No execution analysis saved yet. Run the test when you want to examine the current information; unresolved questions can remain open.</p>}
  </section>{publication?.(result && !view?.stale && !loading && !checking && !running && !readError && !disabled ? result.blocker_count : null)}</>;
}
