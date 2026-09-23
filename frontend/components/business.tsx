"use client";
import Link from "next/link";
import { useCallback, useState } from "react";
import { api, type Proposal } from "@/lib/api";
import { useResource } from "./use-resource";
import { ErrorState, LoadingState } from "./states";
import { ReadinessBadge } from "./readiness";
const loadTasks = (signal: AbortSignal) => api.tasks(signal);
export function BusinessDashboard() {
  const { data, status, retry } = useResource(loadTasks);
  return <><header className="detail-header"><div className="eyebrow accent">BUSINESS WORKSPACE · DEMO</div><h1>Challenges, with possibility.</h1><p className="muted">Clarify your business knowledge, review original proposals, and decide who to work with. This demo shows all businesses’ challenges; no login or ownership checks are applied.</p><div className="challenge-actions"><Link className="button" href="/business/new">New challenge</Link></div></header>{status === "loading" ? <LoadingState /> : status !== "ready" || !data ? <ErrorState retry={retry} /> : !data.length ? <div className="state"><h2>No challenges yet</h2><p>Business challenges will appear here when available.</p></div> : <div className="business-list">{data.map(task => <article key={task.id} className="business-row"><div><span className="industry">{task.industry || "Industry not specified"}</span><h2>{task.title || "Untitled challenge"}</h2><span className="muted text-sm">{task.published ? "Published" : "Unpublished"} · Readiness {task.score}/100</span></div><ReadinessBadge level={task.readiness_level} /><div className="row-actions">{task.published && <Link href={`/challenges/${task.id}`}>Challenge details ↗</Link>}<Link href={`/business/challenges/${task.id}/interview`}>Clarify challenge</Link><Link className="button" href={`/business/challenges/${task.id}/proposals`}>Review proposals</Link></div></article>)}</div>}</>;
}
function PrototypeLink({ value }: { value: string | null }) {
  let safe = false;
  try { safe = ["http:", "https:"].includes(new URL(value || "").protocol); } catch {}
  return safe ? <a href={value!} target="_blank" rel="noopener noreferrer" className="prototype-link">{value}</a> : <span>{value || "Not provided"}</span>;
}
function OriginalProposal({ proposal, team }: { proposal: Proposal; team: string }) {
  return <><div className="eyebrow accent">ORIGINAL STUDENT PROPOSAL</div><h2>{team}</h2><dl className="original-text">{([["solution_idea", "Solution idea"], ["plan", "Implementation plan"], ["timeline", "Timeline"], ["prototype_url", "Prototype URL"]] as const).map(([field, title]) => <div key={field}><dt>{title}</dt><dd>{field === "prototype_url" ? <PrototypeLink value={proposal[field]} /> : proposal[field] || "Not provided"}</dd></div>)}</dl></>;
}
function ProposalReviewCard({ initial, team }: { initial: Proposal; team: string }) {
  const [proposal, setProposal] = useState(initial);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  async function decide(action: "accept" | "reject") {
    if (pending) return; setPending(true); setError("");
    try { setProposal(await api.decide(proposal.id, action)); }
    catch { setError("Decision could not be confirmed. Try again or reload to check its current status."); }
    finally { setPending(false); }
  }
  return <article className="proposal-review" data-testid={`proposal-${proposal.id}`}><div className="proposal-top"><span className={`status-label ${proposal.status}`} role="status">{proposal.status[0].toUpperCase() + proposal.status.slice(1)}</span><span className="muted text-sm">Proposal #{proposal.id}</span></div><OriginalProposal proposal={proposal} team={team} /><div className="decision-actions"><button className="button" disabled={pending || proposal.status === "accepted"} onClick={() => decide("accept")}>Accept</button><button className="button secondary" disabled={pending || proposal.status === "rejected"} onClick={() => decide("reject")}>Reject</button><span className="muted text-sm">{pending ? "Saving decision…" : "You can change this decision later."}</span></div>{error && <p className="form-error" role="alert">{error}</p>}</article>;
}
export function BusinessProposals({ id }: { id: string }) {
  const loader = useCallback((signal: AbortSignal) => Promise.all([api.task(id, signal), api.proposals(id, signal), api.teams(signal)]), [id]);
  const { data, status, retry } = useResource(loader);
  if (status === "loading") return <LoadingState />;
  if (!data || status !== "ready") return <ErrorState notFound={status === "missing"} retry={retry} />;
  const [task, proposals, teams] = data;
  return <><Link className="back-link" href="/business">← Business workspace</Link><header className="detail-header"><div className="eyebrow accent">PROPOSAL REVIEW</div><h1>{task.title || "Untitled challenge"}</h1><p className="muted">The business makes the final decision. Accept one team, multiple teams, or none. Each decision affects only that proposal.</p></header><div className="section-heading"><h2>{proposals.length} original {proposals.length === 1 ? "proposal" : "proposals"}</h2><span className="muted text-sm">Submission order · no ranking</span></div>{proposals.length ? <div className="proposal-grid">{proposals.map(proposal => <ProposalReviewCard key={proposal.id} initial={proposal} team={teams.find(team => team.id === proposal.team_id)?.name || `Team #${proposal.team_id}`} />)}</div> : <div className="state"><h2>No proposals yet</h2><p>Student submissions will appear here. No team has been selected.</p></div>}</>;
}
