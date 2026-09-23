export type Level = "draft" | "working" | "ready" | "priority";
export type Challenge = {
  published: boolean;
  id: number; title: string | null; industry: string | null;
  context: string | null; need: string | null; users: string | null;
  data: string | null; expected_result: string | null; success_criteria: string | null;
  constraints: string | null; contact: string | null; interaction_format: string | null;
  score: number; readiness_level: Level; confirmed_fields: string[]; created_at: string;
};
export type Score = {
  score: number; level: Level;
  breakdown: Record<string, { score: number; max: number; missing: string[]; reason: string }>;
  points_to_next_level: number; next_level: Level | null;
};
export class ApiError extends Error {
  constructor(public status: number, public detail?: string) { super(detail || `API request failed (${status})`); }
}
const base = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const timeout = AbortSignal.timeout(12000);
  const response = await fetch(`${base}${path}`, { signal: signal ? AbortSignal.any([signal, timeout]) : timeout, cache: "no-store" });
  if (!response.ok) throw new ApiError(response.status);
  return response.json() as Promise<T>;
}
export const api = {
  publishTask: (id: string) => post<Challenge>(`/api/tasks/${encodeURIComponent(id)}/publish`),
  unpublishTask: (id: string) => post<Challenge>(`/api/tasks/${encodeURIComponent(id)}/unpublish`),
  createTask: (body: { context: string; title?: string }) => post<Challenge>("/api/tasks", body),
  updateTask: (id: string, body: Partial<Record<KnowledgeField | "title" | "industry", string | null>>) => write<Challenge>(`/api/tasks/${encodeURIComponent(id)}`, "PATCH", body),
  confirmTask: (id: string, fields: KnowledgeField[]) => post<Challenge>(`/api/tasks/${encodeURIComponent(id)}/confirm`, { fields }),
  interview: (id: string, signal?: AbortSignal) => get<Interview>(`/api/tasks/${encodeURIComponent(id)}/interview`, signal),
  startInterview: (id: string) => write<Interview>(`/api/tasks/${encodeURIComponent(id)}/interview/start`, "POST", undefined, 70000),
  respondInterview: (id: string, body: InterviewAnswer) => write<Interview>(`/api/tasks/${encodeURIComponent(id)}/interview/respond`, "POST", body, 70000),
  retryInterview: (id: string) => write<Interview>(`/api/tasks/${encodeURIComponent(id)}/interview/retry`, "POST", undefined, 70000),
  finishInterview: (id: string) => post<Interview>(`/api/tasks/${encodeURIComponent(id)}/interview/finish`),
  stressTest: (id: string, signal?: AbortSignal) => get<ExecutionTest>(`/api/tasks/${encodeURIComponent(id)}/stress-test`, signal),
  runStressTest: (id: string) => write<ExecutionTest>(`/api/tasks/${encodeURIComponent(id)}/stress-test`, "POST", undefined, 70000),
  tasks: (signal?: AbortSignal) => get<Challenge[]>("/api/tasks", signal),
  task: (id: string, signal?: AbortSignal) => get<Challenge>(`/api/tasks/${encodeURIComponent(id)}`, signal),
  teams: (signal?: AbortSignal) => get<Team[]>("/api/teams", signal),
  proposals: (id: string, signal?: AbortSignal) => get<Proposal[]>(`/api/tasks/${encodeURIComponent(id)}/proposals`, signal),
  submit: (id: string, body: Submission) => post<Proposal>(`/api/tasks/${encodeURIComponent(id)}/proposals`, body),
  decide: (id: number, action: "accept" | "reject") => post<Proposal>(`/api/proposals/${id}/${action}`),
  catalog: (params = new URLSearchParams(), signal?: AbortSignal) => get<Challenge[]>(`/api/catalog?${params}`, signal),
  challenge: (id: string, signal?: AbortSignal) => get<Challenge>(`/api/catalog/${encodeURIComponent(id)}`, signal),
  score: (id: string, signal?: AbortSignal) => get<Score>(`/api/tasks/${encodeURIComponent(id)}/score`, signal),
};

export type Team = { id: number; name: string; skills: string | null };
export type Submission = { team_id: number; solution_idea: string; plan: string; timeline: string; prototype_url: string };
export type Proposal = Omit<Submission, "plan" | "timeline" | "prototype_url"> & {
  id: number; task_id: number; status: "pending" | "accepted" | "rejected";
  plan: string | null; timeline: string | null; prototype_url: string | null;
};
async function post<T>(path: string, body?: unknown): Promise<T> {
  return write<T>(path, "POST", body);
}
async function write<T>(path: string, method: "POST" | "PATCH", body?: unknown, timeout = 12000): Promise<T> {
  const response = await fetch(`${base}${path}`, { method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(timeout) });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new ApiError(response.status, typeof error?.detail === "string" ? error.detail : undefined);
  }
  return response.json() as Promise<T>;
}

export type KnowledgeField = "context" | "need" | "users" | "data" | "expected_result" | "success_criteria" | "constraints" | "contact" | "interaction_format";
export type KnowledgeStatus = "OPEN" | "UNKNOWN" | "NEEDS_EXPERT" | "NOT_APPLICABLE" | "CONFLICT" | "CONFIRMED";
export type QuestionDifficulty = "QUICK" | "THINK" | "DEEP" | "EXPERT";
export type KnowledgeItem = {
  field: KnowledgeField; value: string | null; status: KnowledgeStatus;
  source: string | null; source_role: string | null; confirmed: boolean;
  question_difficulty: QuestionDifficulty; expert: string | null; conflicting_source?: string | null;
};
export type InterviewSource = { id: string; text: string; role: string | null; kind: string };
export type InterviewQuestion = { id: string; field: KnowledgeField; text: string; difficulty: QuestionDifficulty; kind: "clarification" | "not_applicable_check" };
export type Interview = {
  task_id: number; status: "active" | "complete" | "paused";
  items: KnowledgeItem[]; sources: InterviewSource[]; questions: InterviewQuestion[];
  error: string | null; completion_reason: string | null;
};
export type InterviewAnswer = {
  question_id: string; action: "answer" | "dont_understand" | "dont_know" | "needs_expert" | "not_applicable";
  answer?: string; expert?: string; source_role?: string;
};

export type ExecutionGateName = "UNDERSTAND" | "START" | "ACCESS" | "VALIDATE" | "DELIVER";
export type ExecutionStatus = "PASS" | "BLOCKED" | "NOT_APPLICABLE";
export type ExecutionSource = {
  id: string; field: KnowledgeField | null; text: string | null; kind: string;
  role: string | null; knowledge_status: KnowledgeStatus | null;
  confirmed: boolean; expert: string | null;
};
export type ExecutionRequirement = {
  gate: ExecutionGateName; field: KnowledgeField; requirement: string;
  status: ExecutionStatus; reason: string; knowledge_status: KnowledgeStatus;
  source_refs: string[]; required_information: string; expert_if_known: string | null;
  evidence: { source_ref: string; quote: string }[];
};
export type ExecutionResult = {
  created_at: string;
  gates: { gate: ExecutionGateName; status: ExecutionStatus; requirements: ExecutionRequirement[] }[];
  gates_passed: number; blocker_count: number; sources: ExecutionSource[];
};
export type ExecutionTest = { task_id: number; result: ExecutionResult | null; stale: boolean; error: string | null };
