import { test, expect } from "@playwright/test";
import path from "path";

// KPI Goals タブ (フォーク独自)。upstream の「KPI Dashboard」= ヘッダ直下の
// KPIストリップとは別物で、config.json の kpi_targets に対する進捗を出す。
const INDEX = `file://${path.resolve(__dirname, "../public/index.html")}`;
const CANVAS_IDS = [
  "#chartGoalsDailyDuration",
  "#chartGoalsDailyCost",
  "#chartGoalsWeeklyDuration",
  "#chartGoalsWeeklyCost",
  "#chartGoalsMonthlyTrend",
];

async function openGoals(page) {
  await page.locator('.vc-tab[data-tab="goals"]').click();
  await expect(page.locator("#tab-goals")).toHaveClass(/active/);
}

test.describe("KPI Goals タブ", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(INDEX);
  });

  test("既定タブを奪っていない", async ({ page }) => {
    await expect(page.locator("#tab-costs")).toHaveClass(/active/);
    await expect(page.locator("#tab-goals")).not.toHaveClass(/active/);
  });

  test("タブバーの末尾にあり、クリックで開く", async ({ page }) => {
    const tabs = page.locator(".vc-tab");
    await expect(tabs.last()).toHaveAttribute("data-tab", "goals");
    await openGoals(page);
  });

  test("進捗カードが2枚、値と目標が埋まっている", async ({ page }) => {
    await openGoals(page);
    const cards = page.locator("#goalsProgressGrid .goals-card");
    await expect(cards).toHaveCount(2);
    for (let i = 0; i < 2; i++) {
      await expect(cards.nth(i).locator(".goals-card-value")).not.toBeEmpty();
      await expect(cards.nth(i).locator(".goals-card-target")).not.toBeEmpty();
      // 進捗バーは3状態のいずれかのクラスを持つ
      await expect(cards.nth(i).locator(".goals-bar")).toHaveClass(
        /(behind|ontrack|ahead)/,
      );
      // 内訳は 日次平均 / 残り / 着地見込み の3項目
      await expect(cards.nth(i).locator(".goals-breakdown dd")).toHaveCount(3);
    }
  });

  test("チャートcanvasが5つ、実サイズを持って描画される", async ({ page }) => {
    await openGoals(page);
    for (const id of CANVAS_IDS) {
      const canvas = page.locator(id);
      await expect(canvas).toBeVisible();
      const box = await canvas.boundingBox();
      expect(box, id).not.toBeNull();
      expect(box!.width, id).toBeGreaterThan(0);
      expect(box!.height, id).toBeGreaterThan(0);
    }
  });

  test("期間フィルタでカードと期間表示が追従する", async ({ page }) => {
    await openGoals(page);
    const value = page.locator("#goalsProgressGrid .goals-card-value").first();
    const meta = page.locator("#vcGoalsMeta");

    const allValue = await value.textContent();
    const allMeta = await meta.textContent();

    await page.locator('.vc-range-btn[data-days="7"]').click();
    await expect(value).not.toHaveText(allValue!);
    const sevenMeta = await meta.textContent();
    expect(sevenMeta).not.toBe(allMeta);

    // 期間は日次系列から取るので、7Dは全期間より必ず短い
    const days = (t: string | null) => Number((t || "").split("/")[0]);
    expect(days(sevenMeta)).toBeLessThan(days(allMeta));
    expect(days(sevenMeta)).toBeGreaterThan(0);
  });

  test("タブ操作を通じてJSエラーが出ない", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(`console: ${m.text()}`);
    });
    await page.reload();
    await openGoals(page);
    await page.locator('.vc-range-btn[data-days="30"]').click();
    await page.locator('.vc-range-btn[data-days="0"]').click();
    expect(errors, errors.join("\n")).toHaveLength(0);
  });
});

test.describe("KPI Goals タブのテーマ追従", () => {
  // 旧実装は色を JS 内にインラインの16進で持っていたため、
  // upstream v1.0.0 で入ったライトテーマで文字が読めなくなる。
  for (const scheme of ["light", "dark"] as const) {
    test(`${scheme}テーマでカードが背景と異なる文字色を持つ`, async ({
      browser,
    }) => {
      const page = await browser.newPage({ colorScheme: scheme });
      await page.goto(INDEX);
      await openGoals(page);
      const colors = await page.evaluate(() => {
        const card = document.querySelector(
          "#goalsProgressGrid .goals-card",
        ) as HTMLElement;
        const value = card.querySelector(".goals-card-value") as HTMLElement;
        return {
          bg: getComputedStyle(card).backgroundColor,
          fg: getComputedStyle(value).color,
        };
      });
      expect(colors.bg).not.toBe(colors.fg);
      expect(colors.bg).not.toBe("rgba(0, 0, 0, 0)");
      await page.close();
    });
  }
});
