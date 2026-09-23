import { test, expect } from "@playwright/test";

test("seeded catalog loads in readiness order", async ({ page }) => {
  await page.goto("/");
  const cards = page.getByTestId("challenge-card");
  await expect(cards).toHaveCount(8);
  await expect(page.getByRole("link", { name: /AI contract review/ })).toBeVisible();
  const scores = await cards.evaluateAll(nodes => nodes.map(n => Number(n.getAttribute("data-score"))));
  expect(scores).toEqual([...scores].sort((a, b) => b - a));
  await page.screenshot({ path: "test-results/catalog-desktop.png", fullPage: true });
});

test("readiness and industry filters use the backend", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("challenge-card")).toHaveCount(8);
  await page.getByLabel("Readiness", { exact: true }).selectOption("draft");
  await expect(page.getByTestId("challenge-card")).toHaveCount(2);
  await page.getByLabel("Industry", { exact: true }).selectOption("education");
  await expect(page.getByTestId("challenge-card")).toHaveCount(1);
  await expect(page.getByTestId("challenge-card")).toContainText("Shymkent college");
  await page.getByLabel("Readiness", { exact: true }).selectOption("priority");
  await expect(page.getByRole("heading", { name: "No challenges found" })).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByTestId("challenge-card")).toHaveCount(8);
});

test("newest sorting matches API", async ({ page, request }) => {
  const response = await request.get("http://127.0.0.1:8000/api/catalog?sort=newest");
  const tasks = await response.json();
  await page.goto("/");
  await page.getByLabel("Sort by").selectOption("newest");
  await expect(page.getByTestId("challenge-card").first()).toContainText(tasks[0].title);
  await expect(page.getByTestId("challenge-card")).toHaveCount(tasks.length);
});

test("details show missing and unconfirmed information honestly", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: /AI contract review/ }).click();
  await expect(page.getByRole("heading", { name: "AI contract review for an Almaty distributor" })).toBeVisible();
  await expect(page.getByText("Not confirmed yet — the business has not provided this information.").first()).toBeVisible();
  await expect(page.getByText("Not confirmed yet", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("meter")).toHaveCount(7);
  await expect(page.getByRole("heading", { name: "What’s behind the score" })).toBeVisible();
  await page.screenshot({ path: "test-results/detail-desktop.png", fullPage: true });
});

test("unknown challenge has a usable not-found state", async ({ page }) => {
  await page.goto("/challenges/999999");
  await expect(page.getByRole("heading", { name: "Challenge unavailable" })).toBeVisible();
  await expect(page.getByRole("alert").getByRole("link", { name: "Explore challenges" })).toHaveAttribute("href", "/");
});

test("backend failure can be retried", async ({ page }) => {
  await page.route("**/api/catalog?*", route => route.abort());
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "We couldn’t connect to the hub" })).toBeVisible();
  await page.unroute("**/api/catalog?*");
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByTestId("challenge-card")).toHaveCount(8);
});

test("empty catalog and loading state", async ({ page }) => {
  await page.route("**/api/catalog?*", async route => {
    await new Promise(resolve => setTimeout(resolve, 500));
    await route.fulfill({ json: [] });
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Loading challenges" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "No challenges found" })).toBeVisible();
});

test("mobile catalog has no horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByTestId("challenge-card")).toHaveCount(8);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.screenshot({ path: "test-results/catalog-mobile.png", fullPage: true });
});
