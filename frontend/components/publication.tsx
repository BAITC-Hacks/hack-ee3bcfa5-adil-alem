"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { Challenge, Interview } from "@/lib/api";
import { ReadinessBadge } from "./readiness";

export function ChallengePublication({ task, interview, blockers, busy, publish, unpublish, saveTitle }: {
  task: Challenge; interview: Interview | null; blockers: number | null; busy: boolean;
  publish: () => void; unpublish: () => void; saveTitle: (title: string) => void;
}) {
  const [title, setTitle] = useState(task.title || "");
  useEffect(() => setTitle(task.title || ""), [task.title]);
  const unresolved = interview?.items.filter(item => item.status !== "NOT_APPLICABLE" && (!item.confirmed || item.status !== "CONFIRMED"));
  return <section className="brief interview-review" aria-labelledby="publication-heading" data-testid="publication">
    <div className="eyebrow accent">MARKETPLACE PUBLICATION</div>
    <h2 id="publication-heading">{task.published ? "Published" : "Share your challenge"}</h2>
    <div className="question-meta"><strong>Readiness: {task.score}/100</strong><ReadinessBadge level={task.readiness_level} /></div>
    <p className="muted text-sm">{blockers === null ? "No current verified execution blocker count available. An execution test is optional for publication." : `Execution blockers: ${blockers}. Blockers do not prevent publication.`}</p>
    {!!unresolved?.length && <p className="muted text-sm">Known unresolved information: {unresolved.map(item => `${item.field.replaceAll("_", " ")} (${item.status === "OPEN" ? "unconfirmed" : item.status.toLowerCase().replaceAll("_", " ")})`).join(", ")}.</p>}
    <p>{task.published ? "Students can view this challenge in the catalog, including missing and unconfirmed information." : "You can publish with unresolved information. Students will see missing and unconfirmed fields. Only a title and saved business need are required."}</p>
    <div className="review-field proposal-form">
      <label htmlFor="publication-title">Challenge title</label>
      <input id="publication-title" value={title} disabled={busy} onChange={event => setTitle(event.target.value)} />
      <div className="review-actions"><button className="button secondary" disabled={busy || title === (task.title || "")} onClick={() => saveTitle(title)}>Save title</button></div>
      <p className="muted text-sm">Review and save the business need in Human review below. Unsaved edits are not published.</p>
    </div>
    <div className="interview-actions">
      {task.published ? <><Link className="button" href={`/challenges/${task.id}`}>View in catalog</Link><button className="button secondary" disabled={busy} onClick={unpublish}>Unpublish</button></> : <button className="button" disabled={busy} onClick={publish}>Publish challenge</button>}
    </div>
  </section>;
}
