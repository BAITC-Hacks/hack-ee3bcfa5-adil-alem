import { test, expect, type APIRequestContext } from "@playwright/test";
import type { Challenge, ExecutionTest, Interview } from "../lib/api";

const backend = "http://127.0.0.1:8000";
const fields = {
  context: "Employees spend time reviewing supplier contracts in our Almaty office.",
  need: "Identify clauses that differ from our approved contract template.",
  users: "Procurement employees who review supplier contracts every week.",
  success_criteria: "The business will check 20 reviewed contracts against its approved review checklist.",
  expected_result: "A list of contract clauses that require attention from the business reviewer.",
  constraints: "Use the business review checklist and keep the work within the supplied contract scope.",
  contact: "Business representative: Dana from the Almaty office.",
  interaction_format: "A scheduled review with the business representative each week.",
};

async function createTask(request: APIRequestContext, title: string, changes: Record<string, string> = {}) {
  const response = await request.post(`${backend}/api/tasks`, { data: { title, ...fields, ...changes } });
  expect(response.status()).toBe(201);
  const task: Challenge = await response.json();
  const confirmed = await request.post(`${backend}/api/tasks/${task.id}/confirm`, { data: { fields: Object.keys(fields) } });
  expect(confirmed.ok()).toBeTruthy();
  return await confirmed.json() as Challenge;
}
async function interviewDataQuestion(request: APIRequestContext, id: number) {
  const response = await request.post(`${backend}/api/tasks/${id}/interview/start`);
  expect(response.ok()).toBeTruthy();
  const state: Interview = await response.json();
  expect(state.error).toBeNull();
  return state.questions.find(question => question.field === "data")!;
}
async function savedResult(request: APIRequestContext, id: number) {
  return await (await request.get(`${backend}/api/tasks/${id}/stress-test`)).json() as ExecutionTest;
}

test("execution diagnostic displays grounded expert blockers and preserves human authority", async ({ page, request }) => {
  const task = await createTask(request, "Execution expert: contract review");
  const question = await interviewDataQuestion(request, task.id);
  const answered = await request.post(`${backend}/api/tasks/${task.id}/interview/respond`, { data: { question_id: question.id, action: "needs_expert", expert: "IT department" } });
  expect(answered.ok()).toBeTruthy();
  let runs = 0;
  page.on("request", request => { if (request.method() === "POST" && request.url().endsWith("/stress-test")) runs++; });
  await page.goto(`/business/challenges/${task.id}/interview`);
  const panel = page.getByTestId("execution-test");
  await expect(panel.getByRole("button", { name: "Run execution test", exact: true })).toBeEnabled();
  expect(runs).toBe(0);
  await panel.getByRole("button", { name: "Run execution test", exact: true }).click();
  await expect(panel).toContainText("4/5 gates passed");
  await expect(panel).toContainText("1 blocker");
  await expect(panel.locator(".execution-gate")).toHaveCount(5);
  const access = page.getByTestId("execution-gate-ACCESS");
  await access.locator(":scope > summary").click();
  await expect(access).toContainText("Student execution may stop here.");
  await expect(access).toContainText("Required information");
  await expect(access).toContainText("NEEDS EXPERT");
  await expect(access).toContainText("Knowledge owner");
  await expect(access).toContainText("IT department");
  await access.getByText(/Show source information/).click();
  await expect(access).toContainText("needs_expert: IT department");
  await expect(panel.getByRole("progressbar")).toHaveCount(0);
  const unchanged: Challenge = await (await request.get(`${backend}/api/tasks/${task.id}`)).json();
  expect(unchanged.score).toBe(task.score);
  expect(unchanged.confirmed_fields).toEqual(task.confirmed_fields);
  const published = await request.post(`${backend}/api/tasks/${task.id}/publish`);
  expect(published.ok()).toBeTruthy();
  expect((await published.json()).published).toBe(true);
  expect((await savedResult(request, task.id)).result?.blocker_count).toBe(1);
  await page.reload();
  await expect(panel).toContainText("4/5 gates passed");
  expect(runs).toBe(1);
  await access.locator(":scope > summary").click();
  await access.getByText(/Show source information/).click();
  await page.screenshot({ path: "test-results/execution-gates.png", fullPage: true });
});

test("saved execution diagnostics become stale on task and knowledge edits with explicit reruns", async ({ page, request }) => {
  const task = await createTask(request, "Execution changes: contract review");
  await interviewDataQuestion(request, task.id);
  let runs = 0;
  page.on("request", request => { if (request.method() === "POST" && request.url().endsWith("/stress-test")) runs++; });
  await page.goto(`/business/challenges/${task.id}/interview`);
  const panel = page.getByTestId("execution-test");
  await panel.getByRole("button", { name: "Run execution test", exact: true }).click();
  await expect(panel).toContainText("4/5 gates passed");
  const original = await savedResult(request, task.id);
  const review = page.getByTestId("review-context");
  await review.locator("textarea").fill("Supplier contract reviews are delayed because comparison work takes too long.");
  await review.getByRole("button", { name: "Save reviewed value" }).click();
  await expect(panel).toContainText("Challenge information changed since this test.");
  expect(runs).toBe(1);
  expect((await savedResult(request, task.id)).result?.created_at).toBe(original.result?.created_at);
  await panel.getByRole("button", { name: "Run execution test again" }).click();
  await expect(panel).toContainText("3/5 gates passed");
  await expect(panel.locator(".execution-stale")).toHaveCount(0);
  expect(runs).toBe(2);
  const data = page.getByTestId("interview-question-data");
  await data.getByRole("button", { name: "Needs another expert", exact: true }).click();
  await data.getByLabel("Expert name or role").fill("IT department");
  await data.getByRole("button", { name: "Mark needs expert" }).click();
  await expect(panel).toContainText("Challenge information changed since this test.");
  expect(runs).toBe(2);
  await panel.getByRole("button", { name: "Run execution test again" }).click();
  await expect(panel.locator(".execution-stale")).toHaveCount(0);
  const access = page.getByTestId("execution-gate-ACCESS");
  await access.locator(":scope > summary").click();
  await expect(access).toContainText("IT department");
  expect(runs).toBe(3);
});

test("design-only scope shows dataset not applicable without an execution blocker", async ({ page, request }) => {
  const task = await createTask(request, "Execution design: information layout", {
    context: "The business wants a clearer layout for its employee information page.",
    need: "Create a visual layout using the supplied text; no existing dataset is required for this design-only brief.",
    expected_result: "A visual layout of the employee information page for business review.",
  });
  await page.goto(`/business/challenges/${task.id}/interview`);
  const panel = page.getByTestId("execution-test");
  await panel.getByRole("button", { name: "Run execution test", exact: true }).click();
  await expect(panel).toContainText("0 blockers");
  const access = page.getByTestId("execution-gate-ACCESS");
  await access.locator(":scope > summary").click();
  await expect(access).toContainText("NOT APPLICABLE");
  await expect(access).not.toContainText("Student execution may stop here.");
  await access.getByText(/Show source information/).click();
  await expect(access).toContainText("no existing dataset is required");
  expect((await (await request.get(`${backend}/api/tasks/${task.id}`)).json()).score).toBe(task.score);
});

test("execution provider failure preserves its previous result and allows explicit retry", async ({ page, request }) => {
  const task = await createTask(request, "Execution outage: supplier contract review");
  await page.goto(`/business/challenges/${task.id}/interview`);
  const panel = page.getByTestId("execution-test");
  await panel.getByRole("button", { name: "Run execution test", exact: true }).click();
  await expect(panel).toContainText("4/5 gates passed");
  const original = await savedResult(request, task.id);
  await panel.getByRole("button", { name: "Run execution test again" }).click();
  await expect(panel.getByRole("alert")).toContainText("temporarily unavailable");
  const refreshed = page.waitForResponse(response => response.request().method() === "GET" && response.url().endsWith("/stress-test"));
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await refreshed;
  await expect(panel.getByRole("alert")).toContainText("temporarily unavailable");
  await expect(panel).toContainText("4/5 gates passed");
  expect((await savedResult(request, task.id)).result?.created_at).toBe(original.result?.created_at);
  await panel.getByRole("button", { name: "Retry execution test" }).click();
  await expect(panel.getByRole("alert")).toHaveCount(0);
  await expect(panel).toContainText("4/5 gates passed");
  expect((await savedResult(request, task.id)).result?.created_at).not.toBe(original.result?.created_at);
});
