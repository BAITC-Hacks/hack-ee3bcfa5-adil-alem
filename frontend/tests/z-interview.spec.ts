import { test, expect } from "@playwright/test";

test("adaptive interview preserves knowledge and needs human confirmation", async ({ page, request }) => {
  await page.goto("/business/new");
  await page.getByLabel("Your description", { exact: true }).fill("We lose track of requests in our Almaty office.");
  await page.getByRole("button", { name: "Start interview", exact: true }).click();
  await expect(page).toHaveURL(/\/business\/challenges\/\d+\/interview$/);
  const id = page.url().split("/").at(-2)!;
  await expect(page.locator(".interview-question")).toHaveCount(3);
  await page.screenshot({ path: "test-results/interview-active.png", fullPage: true });
  expect((await (await request.get(`http://127.0.0.1:8000/api/tasks/${id}`)).json()).score).toBe(0);

  const need = page.getByTestId("interview-question-need");
  const answer = "We need to track each request until the responsible colleague resolves it.";
  await need.locator("textarea").fill(answer);
  await need.getByRole("button", { name: "Answer", exact: true }).click();
  await expect(page.getByTestId("knowledge-need")).toContainText(answer);
  expect((await (await request.get(`http://127.0.0.1:8000/api/tasks/${id}`)).json()).score).toBe(0);

  const users = page.getByTestId("interview-question-users");
  await users.getByRole("button", { name: "I don't understand", exact: true }).click();
  await expect(users).toContainText("Who experiences this problem?");
  await users.getByRole("button", { name: "I don't know", exact: true }).click();
  await expect(page.getByTestId("knowledge-users")).toContainText("Unknown");
  const data = page.getByTestId("interview-question-data");
  await data.getByRole("button", { name: "Needs another expert", exact: true }).click();
  await data.getByLabel("Expert name or role").fill("Our system administrator, Dana");
  await data.getByRole("button", { name: "Mark needs expert" }).click();
  await expect(page.getByTestId("knowledge-data")).toContainText("Our system administrator, Dana");
  await expect(page.locator(".interview-question")).toHaveCount(3);
  await expect(page.getByTestId("interview-question-users")).toHaveCount(0);
  await expect(page.getByTestId("interview-question-data")).toHaveCount(0);

  const constraints = page.getByTestId("interview-question-constraints");
  await constraints.getByRole("button", { name: "Not applicable", exact: true }).click();
  await expect(constraints).toContainText("What makes this information not applicable");
  await constraints.getByRole("button", { name: "Not applicable", exact: true }).click();
  await expect(page.getByTestId("knowledge-constraints")).toContainText("Not applicable");

  const review = page.getByTestId("review-need");
  await expect(review.locator("textarea")).toHaveValue(answer);
  await review.getByRole("button", { name: "Save reviewed value" }).click();
  expect((await (await request.get(`http://127.0.0.1:8000/api/tasks/${id}`)).json()).score).toBe(0);
  await review.getByRole("button", { name: "Confirm field", exact: true }).click();
  await expect(review.getByRole("button", { name: "Confirmed", exact: true })).toBeVisible();
  const confirmed = await (await request.get(`http://127.0.0.1:8000/api/tasks/${id}`)).json();
  expect(confirmed.score).toBe(10);
  await page.getByRole("button", { name: "Finish for now", exact: true }).click();
  await expect(page.getByRole("button", { name: "Resume interview", exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByTestId("knowledge-users")).toContainText("Unknown");
  await expect(page.getByTestId("knowledge-data")).toContainText("Dana");
  const state = await (await request.get(`http://127.0.0.1:8000/api/tasks/${id}/interview`)).json();
  expect(state.status).toBe("paused");
  expect(state.sources.some((source: { text: string }) => source.text === answer)).toBeTruthy();
  await page.screenshot({ path: "test-results/interview-knowledge-map.png", fullPage: true });
});

test("AI outage preserves the draft and offers retry without fake questions", async ({ page, request }) => {
  await page.goto("/business/new");
  const draft = "Demo outage: our college needs to understand missed appointments.";
  await page.getByLabel("Your description", { exact: true }).fill(draft);
  await page.getByRole("button", { name: "Start interview", exact: true }).click();
  await expect(page).toHaveURL(/\/business\/challenges\/\d+\/interview$/);
  await expect(page.getByRole("button", { name: "Retry AI" })).toBeVisible();
  await expect(page.locator(".interview-question")).toHaveCount(0);
  const id = page.url().split("/").at(-2)!;
  expect((await (await request.get(`http://127.0.0.1:8000/api/tasks/${id}`)).json()).context).toBe(draft);
  await page.getByRole("button", { name: "Retry AI" }).click();
  await expect(page.locator(".interview-question")).toHaveCount(3);
  await page.getByRole("button", { name: "Finish for now", exact: true }).click();
  await expect(page.getByRole("button", { name: "Resume interview" })).toBeVisible();
  expect((await (await request.get(`http://127.0.0.1:8000/api/tasks/${id}`)).json()).score).toBe(0);
});
