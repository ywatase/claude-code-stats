import { test, expect } from "@playwright/test";
import fs from "fs";
import path from "path";

// 生成HTMLは JSON を <script> 内にインラインで埋め込む。セッションのテキスト
// (ツールエラーに含まれる貼り付けHTMLなど) に "</script>" や "<!--" が入ると
// スクリプトタグが途中で閉じ、SyntaxError でページ全体が死ぬ。
// extract_stats.py の _embed_json() が "<" を < にエスケープしていることの
// 回帰テスト。project ページは upstream が無対策だった箇所なので必ず含める。
const publicDir = path.resolve(__dirname, "../public");

function syntaxErrorsOf(pageErrors: string[]): string[] {
  return pageErrors.filter(
    (e) =>
      e.includes("SyntaxError") ||
      e.includes("Invalid or unexpected token") ||
      e.includes("Unexpected token"),
  );
}

/** mtime の新しい順に n 件。古いバージョンが残した生成物を拾わないため。 */
function newestPages(dir: string, n: number): string[] {
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((f) => f.endsWith(".html"))
    .map((f) => ({ f, mtime: fs.statSync(path.join(dir, f)).mtimeMs }))
    .sort((a, b) => b.mtime - a.mtime)
    .slice(0, n)
    .map((x) => x.f);
}

test.describe("埋め込みデータのエスケープ", () => {
  test("ダッシュボードが構文エラーなしで読み込まれ、全タブでJSが完走する", async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));
    await page.goto(`file://${path.join(publicDir, "index.html")}`);
    expect(syntaxErrorsOf(errors)).toHaveLength(0);

    // タブは JS が組み立てるので、スクリプトが死んでいれば1つも出ない
    const tabs = page.locator(".vc-tab");
    await expect(tabs).toHaveCount(6);

    // 各タブを開いて描画まで走らせる (JS完走の証拠)
    for (const id of [
      "plan",
      "activity",
      "sessions",
      "insights",
      "goals",
      "costs",
    ]) {
      await page.locator(`.vc-tab[data-tab="${id}"]`).click();
      await expect(page.locator(`#tab-${id}`)).toHaveClass(/active/);
    }
    expect(errors, errors.join("\n")).toHaveLength(0);
  });

  test("最新のセッションページが構文エラーなしで読み込まれる", async ({
    page,
  }) => {
    const dir = path.join(publicDir, "sessions");
    const files = newestPages(dir, 5);
    expect(files.length).toBeGreaterThan(0);

    for (const file of files) {
      const errors: string[] = [];
      page.on("pageerror", (err) => errors.push(err.message));
      await page.goto(`file://${path.join(dir, file)}`);
      expect(syntaxErrorsOf(errors), file).toHaveLength(0);
      page.removeAllListeners("pageerror");
    }
  });

  test("最新のプロジェクトページが構文エラーなしで読み込まれる", async ({
    page,
  }) => {
    const dir = path.join(publicDir, "projects");
    const files = newestPages(dir, 5);
    expect(files.length).toBeGreaterThan(0);

    for (const file of files) {
      const errors: string[] = [];
      page.on("pageerror", (err) => errors.push(err.message));
      await page.goto(`file://${path.join(dir, file)}`);
      expect(syntaxErrorsOf(errors), file).toHaveLength(0);
      page.removeAllListeners("pageerror");
    }
  });

  test("JSONの断片が本文に流出していない", async ({ page }) => {
    // script タグが途中で閉じると、残りのJSONが本文テキストとして描画される
    for (const p of [
      path.join(publicDir, "index.html"),
      ...newestPages(path.join(publicDir, "sessions"), 2).map((f) =>
        path.join(publicDir, "sessions", f),
      ),
      ...newestPages(path.join(publicDir, "projects"), 2).map((f) =>
        path.join(publicDir, "projects", f),
      ),
    ]) {
      await page.goto(`file://${p}`);
      const body = (await page.locator("body").innerText()).slice(0, 200000);
      expect(body, p).not.toContain('"session_id":');
      expect(body, p).not.toContain('"cache_read_tokens":');
    }
  });
});
