# フォーク運用メモ

このリポジトリは [AeternaLabsHQ/claude-code-stats](https://github.com/AeternaLabsHQ/claude-code-stats) のフォークです。
現在のベースは **upstream v1.0.1** (`98affc9`)。

## フォーク独自の変更

| 機能 | 触るファイル | 概要 |
|---|---|---|
| KPI Goals タブ | `templates/dashboard.{html,js,css}`, `locales/*.json`, `claudestats_core/settings.py`, `claudestats_core/aggregate.py`, `config.example.json` | `config.json` の `kpi_targets` に対する月次進捗をカード2枚と5チャートで表示 |
| AI 稼働時間メトリクス | `claudestats_core/sessions.py`, `claudestats_core/aggregate.py` | user → assistant の往復時間 (`ai_duration_min`)。upstream の `duration_min` は実時間なので別物 |
| 埋め込み JSON の `<` エスケープ | `extract_stats.py` | `_embed_json()` に集約。upstream は `</` のみ置換で、project ページは無エスケープだった |
| Playwright E2E | `e2e/`, `playwright.config.ts`, `package.json` | 生成物をブラウザで検証。upstream の pytest とは別軸 |
| lint 設定 | `.pre-commit-config.yaml`, `.rumdl.toml` | 下記参照 |

### 設定

```json
{
  "kpi_targets": {
    "monthly_ai_duration_hours": 160,
    "monthly_cost_jpy": 100000,
    "usd_to_jpy": 150
  }
}
```

**この既定値はプレースホルダなので、`config.json` で自分の目標に置き換えること。**
目標は表示期間の日数で按分される（暦月ちょうどの範囲ならその月の実日数、
それ以外は 30 日換算）。実績が目標に届かなければ全期間が赤（Behind）で表示されるが、
これは正常な動作であって不具合ではない。キーを省略した場合は上記の既定値が入るため、
既存の `config.json` はそのまま動く。

### KPI Goals タブの設計メモ

- **タブ ID は `goals`。** `tests/test_tab_aliases.py` がタブ ID を `id:\s*'([a-z]+)'` で
  抽出するためアンダースコアは使えない。また upstream には別物の「KPI Dashboard」
  （ヘッダ直下の KPI ストリップ、`renderKPI()`）が既にあり、同名だと混同する。
- **`TAB_NAMES` の末尾に置く。** `initTabs()` と `#vcTabs` の IIFE がどちらも
  index 0 を active にするため、先頭に置くと既定タブが変わる。
- **色は `vcColor()` / `_vcLiveVar()` 経由。** upstream v1.0.0 で light/dark 両テーマに
  なったので、インラインの 16 進色はライトテーマで読めなくなる。CSS 側も
  `--bg2` / `--text2` / `--green` などレガシー名を使う（`.vc` / `body.vc-page` が
  テーマ対応の `--vc-*` に再マップしている）。
- **期間は `F.daily_costs` から取る。** `F.kpi.first_session` はセッションの**開始日**なので、
  長期セッションが 1 つあるだけで 7D フィルタが 44 日間と判定され、目標が跳ね上がる。
- **日次系列は `per_day` スライスを優先。** 日跨ぎセッションの AI 時間が開始日に
  全部寄るのを防ぐ。ターンの帰属日はプロンプトが出た日（`daily_message_count` と同じ規則）。

## lint / format の境界

**upstream 管理下のパスは formatter から除外している。** 理由は実測値:

| 対象 | ツール | 整形対象になるファイル数 |
|---|---|---|
| `extract_stats.py` + `claudestats_core/` + `tests/` | `ruff format` | 39 中 **37** |
| `templates/**` | `prettier` | 14 中 **14** |
| `config.example.json` | `prettier` | `18.00` → `18.0` に丸められる |
| `assets/fonts/README.md` | `rumdl` | 裸 URL が `<>` で包まれる |

整形すると upstream との差分が数万行に膨れ、次回の取り込みが不可能になる。
除外は `.pre-commit-config.yaml` の各 formatter hook に個別指定している
（トップレベルの `exclude` にすると secret 検出や JSON 構文チェックまで無効になるため）。

**この境界は Claude Code の編集方法にも影響する。** グローバルの PostToolUse hook は
pre-commit の除外を尊重せず、Edit/Write したファイルに `ruff format` をかける。
`extract_stats.py` / `claudestats_core/**` / `templates/**` / 既存の `tests/**` は
**Bash 経由の置換スクリプトで編集する**こと。新規作成するファイルは Edit/Write で構わない。

## 次回 upstream を取り込むとき

1. `git fetch upstream`（サンドボックス下では失敗するので無効化して実行）
2. `git log --oneline fork-base-v1.0.1..upstream/main` で規模を測る
3. **小規模なら** cherry-pick / merge
4. **大規模再編なら**「新ベース + 独自変更の再適用」方式。v1.0.1 移行時の手順が
   `docs/superpowers/plans/2026-08-18-upstream-v1.0.1-migration.md` に残っている
5. 取り込み後は `git tag -f fork-base-v<version>` を打ち直す

参考タグ:

- `fork-base-v1.0.1` — 現在のベースにした upstream タグ
- `fork-pre-v1.0.1` — v1.0.1 移行前のフォーク先端（v0.8.1 ベース）

### 検証ゲート

```bash
cp config.example.json config.json   # 無ければ。import 時に必要
python3 -m pytest tests/ -q          # upstream 同梱 + フォーク追加分
python3 extract_stats.py             # 実データ生成
pnpm exec playwright test            # 生成物のブラウザ検証
pre-commit run --all-files
git diff --stat v<version> -- extract_stats.py claudestats_core templates tests assets tools locales config.example.json
```

最後の diff に出るのは意図した変更だけであること。整形差分が混ざっていたら
`.pre-commit-config.yaml` の除外を直す。

## 破棄した独自変更

upstream に同等以上のものが入ったため、v1.0.1 移行時に取り込まなかったもの:

- **`claude-fable-5` の料金追加** — upstream `claudestats_core/pricing.py` に数値まで一致で存在
- **モデル ID 正規化** — upstream `pricing.py:resolve_pricing()` が `[1m]` サフィックス・
  日付スタンプ・プロバイダプレフィックスを処理する

## 既知の制約

- `config.json` の `language` に `ja` を指定しても、`locales/` には `en` / `de` しか
  無いためフォールバックする。日本語ロケールは未対応（upstream 由来）。
- upstream への PR は出さない方針（`CLAUDE.md` 参照）。`<` エスケープは upstream の
  実バグだが、フォーク内に留めている。
