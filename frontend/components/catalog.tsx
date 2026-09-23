"use client";
import { useEffect, useState } from "react";
import { api, type Challenge, type Level } from "@/lib/api";
import { ChallengeCard } from "./challenge-card";
import { labels } from "./readiness";
import { ErrorState, LoadingState } from "./states";

export function Catalog() {
  const [tasks, setTasks] = useState<Challenge[]>([]);
  const [industries, setIndustries] = useState<string[]>([]);
  const [level, setLevel] = useState("");
  const [industry, setIndustry] = useState("");
  const [sort, setSort] = useState("readiness");
  const [status, setStatus] = useState("loading");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const refresh = () => { if (document.visibilityState === "visible") setAttempt(value => value + 1); };
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => { window.removeEventListener("focus", refresh); document.removeEventListener("visibilitychange", refresh); };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setStatus("loading");
    const params = new URLSearchParams({ sort });
    if (level) params.set("readiness_level", level);
    if (industry) params.set("industry", industry);
    Promise.all([api.catalog(params, controller.signal), api.catalog(undefined, controller.signal)])
      .then(([filtered, all]) => { if (controller.signal.aborted) return; setTasks(filtered); setIndustries([...new Set(all.map(t => t.industry).filter((v): v is string => !!v))].sort()); setStatus("ready"); })
      .catch(() => { if (!controller.signal.aborted) setStatus("error"); });
    return () => controller.abort();
  }, [level, industry, sort, attempt]);
  return <>
    <section className="intro"><div><div className="eyebrow accent">BUSINESS CHALLENGES. STUDENT INGENUITY.</div><h1>Real challenges.<br /><span>Meaningful possibilities.</span></h1><p>Discover business needs across Kazakhstan and find a challenge<br className="desktop-break" /> where your team’s skills can make a difference.</p></div>
      <aside className="intro-note"><span className="note-symbol" aria-hidden>↗</span><h2>Potential starts with a question.</h2><p>From early ideas to ready-to-build briefs, every stage belongs here.</p><a href="#readiness-guide">Understand readiness <span aria-hidden>→</span></a></aside></section>
    <section aria-label="Challenge catalog"><div className="section-heading"><h2>Explore challenges</h2><span className="live-label"><span className="dot" /> Open marketplace</span></div>
      <div className="filters"><label>Readiness<select aria-label="Readiness" value={level} onChange={e => setLevel(e.target.value)}><option value="">All readiness levels</option>{Object.entries(labels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        <label>Industry<select aria-label="Industry" value={industry} onChange={e => setIndustry(e.target.value)}><option value="">All industries</option>{industries.map(value => <option key={value} value={value}>{value}</option>)}</select></label>
        <label className="sort-control">Sort by<select aria-label="Sort by" value={sort} onChange={e => setSort(e.target.value)}><option value="readiness">Highest readiness</option><option value="newest">Newest first</option></select></label>
      </div>
      {status === "loading" ? <LoadingState /> : status === "error" ? <ErrorState retry={() => setAttempt(a => a + 1)} /> : <><div className="results-line" role="status">{tasks.length} {tasks.length === 1 ? "challenge" : "challenges"}<span>Different stages. Shared ambition.</span></div>
        {tasks.length ? <div className="card-grid">{tasks.map(task => <ChallengeCard key={task.id} task={task} />)}</div> : <div className="state"><h2>No challenges found</h2><p>{level || industry ? "Try a different industry or readiness level." : "Published challenges will appear here when available."}</p>{(level || industry) && <button className="button" onClick={() => { setLevel(""); setIndustry(""); }}>Clear filters</button>}</div>}</>}
    </section>
    <section id="readiness-guide" className="readiness-guide"><div><div className="eyebrow accent">A CLEARER START</div><h2>Readiness, not a ranking of ideas.</h2><p>The score reflects confirmed information available to a team.<br />A lower score means there’s more to clarify—not less potential.</p></div><div className="level-guide">{([["draft", "0–39"], ["working", "40–69"], ["ready", "70–89"], ["priority", "90–100"]] as [Level, string][]).map(([key, range]) => <div key={key}><span className={`legend-dot ${key}`} /><strong>{range}</strong><span>{labels[key]}</span></div>)}</div></section>
  </>;
}
