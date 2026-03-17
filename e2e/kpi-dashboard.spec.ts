import { test, expect } from "@playwright/test";
import path from "path";

// KPI Dashboard タブが正しくレンダリングされることを検証する
test.describe("KPI Dashboard tab", () => {
  test.beforeEach(async ({ page }) => {
    const dashboardPath = path.resolve(__dirname, "../public/dashboard.html");
    await page.goto(`file://${dashboardPath}`);

    // KPI Dashboard タブをクリック
    const kpiTab = page.locator(".tab-btn", {
      hasText: /KPI Dashboard|KPI-Dashboard/,
    });
    await kpiTab.click();
    await expect(page.locator("#tab-kpi_dashboard")).toHaveClass(/active/);
  });

  test("進捗カードが2枚表示される", async ({ page }) => {
    const grid = page.locator("#kpiProgressGrid");
    const cards = grid.locator(".plan-card");
    await expect(cards).toHaveCount(2);

    // 各カードにvalue要素とプログレスバーがある
    for (let i = 0; i < 2; i++) {
      const value = cards.nth(i).locator(".value");
      await expect(value).not.toBeEmpty();
      // プログレスバーの外枠が存在する
      const progressBar = cards.nth(i).locator("div >> div >> div");
      const count = await progressBar.count();
      expect(count).toBeGreaterThan(0);
    }
  });

  test("チャートcanvasが5つ描画される", async ({ page }) => {
    const chartIds = [
      "#chartKpiDailyDuration",
      "#chartKpiDailyCost",
      "#chartKpiWeeklyDuration",
      "#chartKpiWeeklyCost",
      "#chartKpiMonthlyTrend",
    ];
    for (const id of chartIds) {
      const canvas = page.locator(id);
      await expect(canvas).toBeVisible();
    }
  });

  test("期間変更で再描画される", async ({ page }) => {
    // 期間を「This Month」に変更
    const preset = page.locator("#periodPreset");
    await preset.selectOption("month");
    await page.locator("#periodApply").click();

    // KPI Dashboard タブに戻る
    const kpiTab = page.locator(".tab-btn", {
      hasText: /KPI Dashboard|KPI-Dashboard/,
    });
    await kpiTab.click();

    // カードが再描画されている
    const cards = page.locator("#kpiProgressGrid .plan-card");
    await expect(cards).toHaveCount(2);

    // チャートが再描画されている
    await expect(page.locator("#chartKpiDailyDuration")).toBeVisible();
  });

  test("kpi_targets未設定時にエラーにならない", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    page.on("pageerror", (err) => errors.push(err.message));

    // ページをリロードして初期化から再実行
    await page.reload();
    const kpiTab = page.locator(".tab-btn", {
      hasText: /KPI Dashboard|KPI-Dashboard/,
    });
    await kpiTab.click();

    // KPIダッシュボード関連のJavaScriptエラーがないことを確認
    const kpiErrors = errors.filter(
      (e) =>
        e.includes("kpi") ||
        e.includes("KPI") ||
        e.includes("renderKpiDashboard") ||
        e.includes("Cannot read"),
    );
    expect(kpiErrors).toHaveLength(0);
  });
});
