import { test, expect } from "@playwright/test";
import fs from "fs";
import path from "path";

// 生成HTMLは JSON を <script> 内にインラインで埋め込む。セッションのテキスト
// (ツールエラーに含まれる貼り付けHTMLなど) に "</script>" や "<!--" が入ると
// スクリプトタグが途中で閉じ、SyntaxError でページ全体が死ぬ。
// extract_stats.py 側で "<" を < にエスケープしていることの回帰テスト。
const publicDir = path.resolve(__dirname, "../public");

function syntaxErrorsOf(pageErrors: string[]): string[] {
  return pageErrors.filter(
    (e) =>
      e.includes("SyntaxError") ||
      e.includes("Invalid or unexpected token") ||
      e.includes("Unexpected token"),
  );
}

test.describe("埋め込みデータのエスケープ", () => {
  test("ダッシュボードが構文エラーなしで読み込まれ、JSが完走する", async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));
    await page.goto(`file://${path.join(publicDir, "index.html")}`);
    expect(syntaxErrorsOf(errors)).toHaveLength(0);

    // タブ切り替えは initTabs() 由来なので、スクリプトが死んでいれば反応しない
    const secondTab = page.locator(".tab-btn").nth(1);
    await secondTab.click();
    await expect(secondTab).toHaveClass(/active/);
  });

  test("最新のセッションページが構文エラーなしで読み込まれる", async ({
    page,
  }) => {
    const sessionsDir = path.join(publicDir, "sessions");
    if (!fs.existsSync(sessionsDir)) test.skip();
    const files = fs
      .readdirSync(sessionsDir)
      .filter((f) => f.endsWith(".html"))
      .map((f) => ({
        f,
        mtime: fs.statSync(path.join(sessionsDir, f)).mtimeMs,
      }))
      .sort((a, b) => b.mtime - a.mtime)
      .slice(0, 5)
      .map((x) => x.f);
    expect(files.length).toBeGreaterThan(0);

    for (const file of files) {
      const errors: string[] = [];
      page.on("pageerror", (err) => errors.push(err.message));
      await page.goto(`file://${path.join(sessionsDir, file)}`);
      expect(syntaxErrorsOf(errors), file).toHaveLength(0);
      page.removeAllListeners("pageerror");
    }
  });
});
