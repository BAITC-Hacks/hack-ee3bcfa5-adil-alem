import Link from "next/link";
import type { Challenge } from "@/lib/api";
import { ReadinessBadge, ReadinessScore } from "./readiness";
export function ChallengeCard({ task }: { task: Challenge }) {
  return <Link href={`/challenges/${task.id}`} className="challenge-card" data-testid="challenge-card" data-score={task.score}>
    <div className="flex items-center justify-between gap-3"><span className="industry">{task.industry || "Industry not specified"}</span><span className="arrow" aria-hidden>↗</span></div>
    <h2>{task.title || "Untitled challenge"}</h2>
    <p className="preview">{task.need || task.context || "Business need not confirmed yet."}</p>
    <div className="card-facts"><span>{task.data ? "Data described" : "Data to clarify"}</span><span>{task.confirmed_fields.length} fields confirmed</span></div>
    <div className="card-bottom"><div><span className="eyebrow">READINESS</span><ReadinessScore score={task.score} level={task.readiness_level} /></div><ReadinessBadge level={task.readiness_level} /></div>
  </Link>;
}
