# Project Rules

## Git / GitHub

- PR は必ず `origin` (ywatase/claude-code-stats) に対して作成すること。`upstream` への PR は禁止。
  - `gh pr create` 実行時は `-R ywatase/claude-code-stats` を指定すること。
- **`main` は upstream/main のミラー。** 直接コミットも merge もしない。
  フォークの統合ブランチは `fork`（GitHub の既定ブランチ）。新規 PR の base は `fork`。
  - フォーク差分は `git diff main..fork` で取れる。

## フォーク運用

- 独自機能の一覧、lint 境界、次回 upstream 取り込み手順は `docs/fork-notes.md` を参照。
- **upstream 管理下のファイルは Edit/Write ツールで編集しないこと。** 対象は
  `extract_stats.py`、`claudestats_core/**`、`templates/**`、既存の `tests/**`。
  グローバル hook が `ruff format` / prettier をファイル全体にかけ、upstream との
  差分が数万行に膨れる。Bash 経由の置換スクリプトで編集する。
- `python3 -m pytest tests/` の実行には `config.json` が必要
  (`extract_stats.py` が import 時に読むため)。
