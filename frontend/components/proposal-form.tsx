"use client";
import Link from "next/link";
import { useCallback, useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { useResource } from "./use-resource";
import { ErrorState, LoadingState } from "./states";
import { ReadinessBadge, ReadinessScore } from "./readiness";
export function ProposalForm({ id }: { id: string }) {
  const loader = useCallback((signal: AbortSignal) => Promise.all([api.challenge(id, signal), api.teams(signal)]), [id]);
  const { data, status, retry } = useResource(loader);
  const [sending, setSending] = useState(false);
  const lock = useRef(false);
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (lock.current) return;
    const form = new FormData(event.currentTarget);
    const team = Number(form.get("team"));
    const fields = { solution_idea: String(form.get("solution_idea") || ""), plan: String(form.get("plan") || ""), timeline: String(form.get("timeline") || ""), prototype_url: String(form.get("prototype_url") || "") };
    if (!team || Object.values(fields).some(value => !value.trim())) { setError("Select a team and complete every field with nonblank information."); return; }
    try { const url = new URL(fields.prototype_url); if (!["http:", "https:"].includes(url.protocol)) throw new Error(); }
    catch { setError("Enter a valid http or https prototype URL."); return; }
    lock.current = true; setSending(true); setError("");
    try { await api.submit(id, { team_id: team, ...fields }); setSubmitted(true); }
    catch (err) { setError(err instanceof ApiError && err.status === 409 ? "This challenge is no longer published. Your proposal was not submitted." : err instanceof ApiError && err.status === 422 ? "Please check all proposal fields and try again." : "Submission could not be confirmed. Your text is kept here. Check with the business before retrying to avoid a duplicate."); }
    finally { setSending(false); lock.current = false; }
  }
  if (status === "loading") return <LoadingState />;
  if (!data || status !== "ready") return <ErrorState notFound={status === "missing"} retry={retry} />;
  const [task, teams] = data;
  if (submitted) return <div className="state" role="status"><h1>Proposal submitted</h1><p>Your original proposal is pending a manual business decision.</p><Link className="button" href={`/challenges/${id}`}>Back to challenge</Link><Link className="text-button" href="/">Explore challenges</Link></div>;
  return <><Link className="back-link" href={`/challenges/${id}`}>← Back to challenge</Link><header className="detail-header"><div className="eyebrow accent">STUDENT PROPOSAL</div><h1>Turn your idea into a proposal.</h1><p className="muted">Share your approach in your own words. The business makes the final decision.</p></header><div className="detail-layout"><form onSubmit={submit} className="brief proposal-form"><h2>Your original proposal</h2><p className="muted text-sm">Your submission is shared with the business as written.</p><fieldset disabled={sending || !teams.length}><label>Team<select aria-label="Team" name="team" defaultValue="" required><option value="" disabled>Select your team</option>{teams.map(team => <option key={team.id} value={team.id}>{team.name}</option>)}</select></label>{!teams.length && <p role="status">No teams are available yet. A team must be added before you can submit.</p>}<label>Solution idea<textarea name="solution_idea" required rows={5} /></label><label>Implementation plan<textarea name="plan" required rows={5} /></label><label>Timeline<input name="timeline" required placeholder="For example: three weeks, with a demo in week two" /></label><label>Prototype URL<input name="prototype_url" required type="url" placeholder="https://example.com/your-prototype" /></label>{error && <p className="form-error" role="alert">{error}</p>}<button className="button" type="submit">{sending ? "Submitting…" : "Submit proposal"}</button></fieldset></form><aside className="readiness-panel"><div className="eyebrow">YOUR CHALLENGE</div><h2 className="reference-title">{task.title}</h2><ReadinessScore score={task.score} level={task.readiness_level} /><ReadinessBadge level={task.readiness_level} />{([ ["expected_result", "Expected result"], ["constraints", "Known constraints"] ] as const).map(([field, label]) => <section className="reference-field" key={field}><h3>{label}</h3><p>{task[field] || "Not confirmed yet"}</p>{task[field] && !task.confirmed_fields.includes(field) && <span className="unconfirmed-label">Not confirmed yet</span>}</section>)}<p className="panel-description">Every readiness level is open for proposals. Unknown information is an opportunity to ask questions.</p></aside></div></>;
}
