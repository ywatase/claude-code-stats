import { test, expect } from "@playwright/test";
import path from "path";

// Plan & Billing タブが正しくレンダリングされることを検証する
test.describe("Plan & Billing tab", () => {
  test.beforeEach(async ({ page }) => {
    const dashboardPath = path.resolve(__dirname, "../public/dashboard.html");
    await page.goto(`file://${dashboardPath}`);

    // Plan & Billing タブをクリック
    const planTab = page.locator(".tab-btn", { hasText: /Plan|プラン/ });
    await planTab.click();
    await expect(page.locator("#tab-plan")).toHaveClass(/active/);
  });

  test("KPIカードが4つ表示される", async ({ page }) => {
    const kpiCards = page.locator("#planKpi .plan-card");
    await expect(kpiCards).toHaveCount(4);

    // 各カードにvalue要素がある
    for (let i = 0; i < 4; i++) {
      const value = kpiCards.nth(i).locator(".value");
      await expect(value).not.toBeEmpty();
    }
  });

  test("Billing progressセクションが表示される", async ({ page }) => {
    const billingProgress = page.locator("#billingProgress");

    // プログレスバーが存在する
    await expect(billingProgress.locator(".progress-bar-outer")).toBeVisible();
    await expect(billingProgress.locator(".progress-bar-inner")).toBeVisible();

    // 統計項目が表示される
    const statItems = billingProgress.locator(".stat-item");
    await expect(statItems).not.toHaveCount(0);
  });

  test("API Cost vs Plan Cost 比較バーが表示される", async ({ page }) => {
    const comparison = page.locator("#planComparison");

    // 比較バーが少なくとも1つ存在する
    const barRows = comparison.locator(".bar-row");
    const count = await barRows.count();
    expect(count).toBeGreaterThan(0);
  });

  test("チャートcanvasが描画される", async ({ page }) => {
    // Chart.jsがcanvasに描画すると幅/高さが設定される
    const savingsChart = page.locator("#chartPlanSavings");
    await expect(savingsChart).toBeVisible();

    const costPerDayChart = page.locator("#chartCostPerDay");
    await expect(costPerDayChart).toBeVisible();
  });

  test("Period Detailテーブルに行データがある", async ({ page }) => {
    const rows = page.locator("#planTableBody tr");
    const count = await rows.count();
    expect(count).toBeGreaterThan(0);
  });

  test("plan_cost_eurがnullでもエラーにならない", async ({ page }) => {
    // コンソールエラーを監視
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    page.on("pageerror", (err) => errors.push(err.message));

    // ページをリロードして初期化から再実行
    await page.reload();
    const planTab = page.locator(".tab-btn", { hasText: /Plan|プラン/ });
    await planTab.click();

    // JavaScriptエラーがないことを確認
    const planErrors = errors.filter(
      (e) =>
        e.includes("toFixed") || e.includes("null") || e.includes("renderPlan"),
    );
    expect(planErrors).toHaveLength(0);
  });
});
