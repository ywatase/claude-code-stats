import { test, expect } from "@playwright/test";
import path from "path";

test.describe("KPI Dashboard tab", () => {
  test.beforeEach(async ({ page }) => {
    const dashboardPath = path.resolve(__dirname, "../public/index.html");
    await page.goto(`file://${dashboardPath}`);
    const kpiTab = page.locator(".tab-btn", {
      hasText: /KPI Dashboard|KPI-Dashboard/,
    });
    await kpiTab.click();
    await expect(page.locator("#tab-kpi_dashboard")).toHaveClass(/active/);
  });

  test("JSエラーなしでページが読み込まれる", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));
    await page.reload();
    const kpiTab = page.locator(".tab-btn", {
      hasText: /KPI Dashboard|KPI-Dashboard/,
    });
    await kpiTab.click();
    await page.waitForTimeout(500);
    const jsErrors = errors.filter(
      (e) =>
        e.includes("ReferenceError") ||
        e.includes("TypeError") ||
        e.includes("Cannot read"),
    );
    expect(jsErrors).toHaveLength(0);
  });

  test("進捗カードが2枚表示される", async ({ page }) => {
    const grid = page.locator("#kpiProgressGrid");
    const cards = grid.locator(".plan-card");
    await expect(cards).toHaveCount(2);
    for (let i = 0; i < 2; i++) {
      await expect(cards.nth(i).locator(".value")).not.toBeEmpty();
    }
  });

  test("チャートcanvasが5つ描画される", async ({ page }) => {
    for (const id of [
      "#chartKpiDailyDuration",
      "#chartKpiDailyCost",
      "#chartKpiWeeklyDuration",
      "#chartKpiWeeklyCost",
      "#chartKpiMonthlyTrend",
    ]) {
      await expect(page.locator(id)).toBeVisible();
    }
  });

  test("タイムレンジ変更後もKPIダッシュボードが正常動作する", async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));
    await page.locator("button", { hasText: "30D" }).click();
    await page.waitForTimeout(300);
    const kpiTab = page.locator(".tab-btn", {
      hasText: /KPI Dashboard|KPI-Dashboard/,
    });
    await kpiTab.click();
    await expect(page.locator("#kpiProgressGrid .plan-card")).toHaveCount(2);
    await expect(page.locator("#chartKpiDailyDuration")).toBeVisible();
    expect(errors).toHaveLength(0);
  });
});
