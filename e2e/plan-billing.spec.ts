import { test, expect } from "@playwright/test";
import path from "path";

// Plan & Billing タブが正しくレンダリングされることを検証する。
// v1.0.1 でタブバーは .vc-tab に移り (.tabs は display:none)、
// planComparison セクションは廃止された。
const INDEX = `file://${path.resolve(__dirname, "../public/index.html")}`;

test.describe("Plan & Billing タブ", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(INDEX);
    await page.locator('.vc-tab[data-tab="plan"]').click();
    await expect(page.locator("#tab-plan")).toHaveClass(/active/);
  });

  test("KPIカードが表示され、値が空でない", async ({ page }) => {
    const cards = page.locator("#planKpi .plan-card");
    const count = await cards.count();
    expect(count).toBeGreaterThan(0);
    for (let i = 0; i < count; i++) {
      await expect(cards.nth(i).locator(".value")).not.toBeEmpty();
    }
  });

  test("Billing progress セクションが表示される", async ({ page }) => {
    const billing = page.locator("#billingProgress");
    await expect(billing).toBeVisible();
    await expect(billing.locator(".stat-item").first()).toBeVisible();
  });

  test("チャートcanvasが実サイズを持って描画される", async ({ page }) => {
    for (const id of ["#chartPlanSavings", "#chartCostPerDay"]) {
      const canvas = page.locator(id);
      await expect(canvas).toBeVisible();
      const box = await canvas.boundingBox();
      expect(box, id).not.toBeNull();
      expect(box!.width, id).toBeGreaterThan(0);
    }
  });

  test("Period Detail テーブルに行データがある", async ({ page }) => {
    const rows = page.locator("#planTableBody tr");
    expect(await rows.count()).toBeGreaterThan(0);
  });

  test("プラン費用が未設定でも描画でエラーにならない", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(m.text());
    });
    page.on("pageerror", (err) => errors.push(err.message));

    await page.reload();
    await page.locator('.vc-tab[data-tab="plan"]').click();
    await expect(page.locator("#tab-plan")).toHaveClass(/active/);

    const planErrors = errors.filter(
      (e) =>
        e.includes("toFixed") || e.includes("null") || e.includes("renderPlan"),
    );
    expect(planErrors, planErrors.join("\n")).toHaveLength(0);
  });
});
