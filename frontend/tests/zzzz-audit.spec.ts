import { test, expect } from "@playwright/test";
const base = "http://127.0.0.1:8000";

test("proposal draft and submission receipt survive reload without duplicate submission", async ({ page, request }) => {
  const task = await (await request.post(`${base}/api/tasks`, { data: { title: "Audit proposal persistence", need: "Compare supplier clauses with the agreed template.", published: true } })).json();
  await page.goto(`/challenges/${task.id}/propose`);
  await page.getByLabel("Team", { exact: true }).selectOption({ label: "Alatau NLP Lab" });
  const text = "Қазақша ұсыныс — русский текст 🚀\n<script>alert('test')</script> **Original**";
  await page.getByLabel("Solution idea", { exact: true }).fill(text);
  await page.getByLabel("Implementation plan", { exact: true }).fill("Review materials\nDiscuss results");
  await page.getByLabel("Timeline", { exact: true }).fill("Two weeks");
  await page.getByLabel("Prototype URL", { exact: true }).fill("https://example.com/audit");
  await page.reload();
  await expect(page.getByLabel("Solution idea", { exact: true })).toHaveValue(text);
  let posts = 0;
  page.on("request", r => { if (r.method() === "POST" && r.url().endsWith("/proposals")) posts++; });
  await expect(page.getByRole("button", { name: "Submit proposal", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Submit proposal", exact: true }).evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
  await expect(page.getByRole("heading", { name: "Proposal submitted" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Proposal submitted" })).toBeVisible();
  const proposals = await (await request.get(`${base}/api/tasks/${task.id}/proposals`)).json();
  expect(proposals).toHaveLength(1);
  expect(proposals[0].solution_idea).toBe(text);
  expect(posts).toBe(1);
  await page.getByRole("button", { name: "Write another proposal" }).click();
  await page.getByLabel("Team", { exact: true }).selectOption({ label: "Alatau NLP Lab" });
  await page.getByLabel("Solution idea", { exact: true }).fill("Second original idea from the same team.");
  await page.getByLabel("Implementation plan", { exact: true }).fill("Review and discuss.");
  await page.getByLabel("Timeline", { exact: true }).fill("Three weeks");
  await page.getByLabel("Prototype URL", { exact: true }).fill("javascript:alert(1)");
  await page.getByRole("button", { name: "Submit proposal", exact: true }).click();
  await expect(page.locator(".form-error")).toContainText("http or https");
  await page.getByLabel("Prototype URL", { exact: true }).fill("https://example.com/second");
  await page.getByRole("button", { name: "Submit proposal", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Proposal submitted" })).toBeVisible();
  const both = await (await request.get(`${base}/api/tasks/${task.id}/proposals`)).json();
  expect(both).toHaveLength(2);
  expect(both[0].team_id).toBe(both[1].team_id);
  expect(both[0].solution_idea).toBe(text);
  await request.post(`${base}/api/proposals/${both[1].id}/accept`);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Proposal submitted" })).toBeVisible();
  await expect(page.locator("main")).not.toContainText("is pending");
  await request.post(`${base}/api/tasks/${task.id}/unpublish`);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Proposal submitted" })).toBeVisible();
});

test("refresh during an execution response preserves server result and never reruns AI", async ({ page, request }) => {
  const task = await (await request.post(`${base}/api/tasks`, { data: { title: "Audit slow execution", context: "Employees review contracts.", need: "Identify clauses different from the approved template." } })).json();
  await page.goto(`/business/challenges/${task.id}/interview`);
  let posts = 0;
  let stored!: () => void;
  const saved = new Promise<void>(resolve => { stored = resolve; });
  await page.route(`**/api/tasks/${task.id}/stress-test`, async route => {
    if (route.request().method() !== "POST") return route.continue();
    posts++;
    const response = await route.fetch();
    stored();
    await new Promise(resolve => setTimeout(resolve, 700));
    await route.fulfill({ response }).catch(() => {});
  });
  await expect(page.getByRole("button", { name: "Run execution test", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Run execution test", exact: true }).evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
  await saved;
  await page.reload();
  await expect(page.getByTestId("execution-test")).toContainText("/5 gates passed");
  await page.waitForTimeout(900);
  expect(posts).toBe(1);
  await expect(page.getByTestId("execution-test")).not.toContainText("No execution analysis saved yet");
});

test("all readiness filters and republishing remain consistent without polling", async ({ page, request }) => {
  let calls = 0;
  page.on("request", r => { if (r.url().includes("/api/catalog")) calls++; });
  await page.goto("/");
  for (const level of ["draft", "working", "ready", "priority"]) {
    await page.getByLabel("Readiness", { exact: true }).selectOption(level);
    await expect(page.getByTestId("challenge-card").first()).toBeVisible();
    const scores = await page.getByTestId("challenge-card").evaluateAll(cards => cards.map(card => Number(card.getAttribute("data-score"))));
    const range = { draft: [0, 39], working: [40, 69], ready: [70, 89], priority: [90, 100] }[level]!;
    expect(scores.every(score => score >= range[0] && score <= range[1])).toBe(true);
  }
  const before = calls;
  await page.waitForTimeout(700);
  expect(calls).toBe(before);
  const task = await (await request.post(`${base}/api/tasks`, { data: { title: "Audit republish", need: "Check supplier documents." } })).json();
  for (const action of ["publish", "unpublish", "publish"]) {
    const current = await (await request.post(`${base}/api/tasks/${task.id}/${action}`)).json();
    expect(current.score).toBe(0);
    expect((await request.get(`${base}/api/catalog/${task.id}`)).status()).toBe(action === "publish" ? 200 : 404);
  }
});

test("open public detail is revalidated when returning after unpublication", async ({ page, request }) => {
  const task = await (await request.post(`${base}/api/tasks`, { data: { title: "Audit catalog freshness", need: "Review existing supplier documents.", published: true } })).json();
  await page.goto(`/challenges/${task.id}`);
  await expect(page.getByRole("heading", { name: task.title, exact: true })).toBeVisible();
  await request.post(`${base}/api/tasks/${task.id}/unpublish`);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("link", { name: "Submit proposal", exact: true })).toHaveCount(0);
  await expect(page.locator("main")).toContainText(/not found|unavailable/i);
});

test("unsaved human review survives reload and same-tab navigation", async ({ page, request }) => {
  const task = await (await request.post(`${base}/api/tasks`, { data: { title: "Audit review recovery", context: "Employees review supplier contracts." } })).json();
  await page.goto(`/business/challenges/${task.id}/interview`);
  const review = page.getByTestId("review-need");
  const value = "Нужно сравнивать пункты с утверждённым шаблоном договора.";
  await review.locator("textarea").fill(value);
  await page.reload();
  await expect(review.locator("textarea")).toHaveValue(value);
  await page.getByRole("link", { name: /Business workspace/ }).click();
  await page.goBack();
  await expect(review.locator("textarea")).toHaveValue(value);
  await review.getByRole("button", { name: "Save reviewed value" }).click();
  await expect(review.getByRole("button", { name: "Confirm field", exact: true })).toBeEnabled();
  await review.getByRole("button", { name: "Confirm field", exact: true }).evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
  await expect(review.getByRole("button", { name: "Confirmed", exact: true })).toBeVisible();
  await page.reload();
  await expect(review.locator("textarea")).toHaveValue(value);
  expect((await (await request.get(`${base}/api/tasks/${task.id}`)).json()).score).toBe(10);
});

test("long unbroken and HTML-looking content stays text and within the viewport", async ({ page, request }) => {
  const title = "Ұ".repeat(1500);
  const task = await (await request.post(`${base}/api/tasks`, { data: { title, need: "<img src=x onerror=alert(1)> **Markdown** 🚀 " + "x".repeat(15000), published: true } })).json();
  let dialogs = 0;
  page.on("dialog", async dialog => { dialogs++; await dialog.dismiss(); });
  await page.goto(`/challenges/${task.id}`);
  await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
  await expect(page.locator("main img")).toHaveCount(0);
  expect(dialogs).toBe(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});
