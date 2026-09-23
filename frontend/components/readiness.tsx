import type { Level, Score } from "@/lib/api";
export const labels: Record<Level, string> = { draft: "Needs clarification", working: "Working", ready: "Ready", priority: "Priority" };
export function ReadinessBadge({ level }: { level: Level }) {
  return <span className={`badge ${level}`}><span className="dot" />{labels[level]}</span>;
}
export function ReadinessScore({ score, level }: { score: number; level: Level }) {
  return <div className={`score ${level}`} aria-label={`Readiness ${score} out of 100`}><strong>{score}</strong><span>/100</span></div>;
}
const categories: Record<string, string> = { context_need: "Context & need", data: "Data & materials", expected_result: "Expected result", success_criteria: "Success criteria", constraints: "Constraints", users: "Target users", business_connection: "Business connection" };
export function ScoreBreakdown({ result }: { result: Score }) {
  return <div className="breakdown">{Object.entries(result.breakdown).map(([key, value]) => <div key={key}>
    <div className="flex justify-between gap-3 text-sm"><span>{categories[key] || key}</span><strong>{value.score}<span className="muted"> / {value.max}</span></strong></div>
    <meter min={0} max={value.max} value={value.score} aria-label={categories[key] || key} />
    <details><summary>How this is calculated</summary><p>{value.reason}</p></details>
  </div>)}</div>;
}
