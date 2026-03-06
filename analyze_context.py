#!/usr/bin/env python3
"""
Claude Code Context Consumption Analyzer

特定セッションのコンテキスト消費パターンを分析し、
コンパクション（コンテキスト圧縮）の原因を特定する CLI ツール。

依存: stdlib のみ
"""

import argparse
import bisect
import json
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

CLAUDE_DIR = Path("~/.claude").expanduser()
PROJECTS_DIR = CLAUDE_DIR / "projects"
HISTORY_JSONL = CLAUDE_DIR / "history.jsonl"

# ── Pricing (USD per 1M tokens) ───────────────────────────────────────────
PRICING = {
    "claude-opus-4-6": {
        "input": 5.00, "output": 25.00,
        "cache_read": 0.50, "cache_write_5m": 6.25, "cache_write_1h": 10.00,
        "display": "Opus 4.6",
    },
    "claude-opus-4-5-20251101": {
        "input": 5.00, "output": 25.00,
        "cache_read": 0.50, "cache_write_5m": 6.25, "cache_write_1h": 10.00,
        "display": "Opus 4.5",
    },
    "claude-sonnet-4-6": {
        "input": 3.00, "output": 15.00,
        "cache_read": 0.30, "cache_write_5m": 3.75, "cache_write_1h": 6.00,
        "display": "Sonnet 4.6",
    },
    "claude-sonnet-4-5-20250929": {
        "input": 3.00, "output": 15.00,
        "cache_read": 0.30, "cache_write_5m": 3.75, "cache_write_1h": 6.00,
        "display": "Sonnet 4.5",
    },
    "claude-haiku-4-5-20251001": {
        "input": 1.00, "output": 5.00,
        "cache_read": 0.10, "cache_write_5m": 1.25, "cache_write_1h": 2.00,
        "display": "Haiku 4.5",
    },
}

DEFAULT_PRICING = {
    "input": 5.00, "output": 25.00,
    "cache_read": 0.50, "cache_write_5m": 6.25, "cache_write_1h": 10.00,
    "display": "Unknown",
}


def get_model_display(model_id):
    return PRICING.get(model_id, DEFAULT_PRICING)["display"]


def calc_cost(model_id, usage):
    """Calculate cost for a single API call based on usage tokens."""
    p = PRICING.get(model_id, DEFAULT_PRICING)
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0)
    cache_creation = usage.get("cache_creation_input_tokens", 0)
    cost = (
        input_tokens * p["input"] / 1_000_000
        + output_tokens * p["output"] / 1_000_000
        + cache_read * p["cache_read"] / 1_000_000
        + cache_creation * p["cache_write_5m"] / 1_000_000
    )
    return cost


def project_display_name(project_path):
    """Extract a short display name from a project path."""
    if not project_path:
        return "Unknown"
    p = project_path.replace("\\", "/")
    parts = p.rstrip("/").split("/")
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return parts[-1] if parts else project_path


# ── Session Search ─────────────────────────────────────────────────────────

def find_all_session_files():
    """Walk PROJECTS_DIR and return {session_id: path} mapping."""
    result = {}
    if not PROJECTS_DIR.exists():
        return result
    for proj_dir in PROJECTS_DIR.iterdir():
        if not proj_dir.is_dir():
            continue
        for jsonl_file in proj_dir.glob("*.jsonl"):
            stem = jsonl_file.stem
            result[stem] = jsonl_file
    return result


def load_history_sessions():
    """Load history.jsonl and return list of session info dicts (deduped by sessionId)."""
    sessions = {}
    if not HISTORY_JSONL.exists():
        return []
    with open(HISTORY_JSONL, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = obj.get("sessionId", "")
            if not sid:
                continue
            ts = obj.get("timestamp", 0)
            if sid not in sessions or ts > sessions[sid]["timestamp"]:
                sessions[sid] = {
                    "sessionId": sid,
                    "project": obj.get("project", ""),
                    "display": obj.get("display", ""),
                    "timestamp": ts,
                }
    return sorted(sessions.values(), key=lambda x: x["timestamp"], reverse=True)


def find_session_file(session_id):
    """Find a session JSONL file by exact or prefix match.

    Returns (path, matched_session_id) or (None, None).
    """
    all_files = find_all_session_files()

    # 1. Exact match
    if session_id in all_files:
        return all_files[session_id], session_id

    # 2. Prefix match
    matches = [(sid, path) for sid, path in all_files.items() if sid.startswith(session_id)]
    if len(matches) == 1:
        return matches[0][1], matches[0][0]
    if len(matches) > 1:
        print(f"複数のセッションが一致しました (prefix: {session_id}):")
        for sid, path in sorted(matches):
            print(f"  {sid}")
        return None, None

    # 3. history.jsonl からプロジェクト横断検索
    history = load_history_sessions()
    for entry in history:
        sid = entry["sessionId"]
        if sid.startswith(session_id):
            if sid in all_files:
                return all_files[sid], sid
            # history にはあるがファイルがない場合: プロジェクトパスから推定
            proj = entry.get("project", "")
            if proj:
                proj_dir_name = proj.replace("/", "-").lstrip("-")
                candidate = PROJECTS_DIR / proj_dir_name / f"{sid}.jsonl"
                if candidate.exists():
                    return candidate, sid

    return None, None


def list_recent_sessions(project_filter=None, limit=20):
    """List recent sessions from history.jsonl with file info."""
    history = load_history_sessions()
    all_files = find_all_session_files()

    results = []
    for entry in history:
        sid = entry["sessionId"]
        proj = entry.get("project", "")
        if project_filter and project_filter.lower() not in proj.lower():
            continue
        file_path = all_files.get(sid)
        try:
            file_size = file_path.stat().st_size if file_path else None
        except OSError:
            file_size = None
        results.append({
            "sessionId": sid,
            "project": proj,
            "display_name": project_display_name(proj),
            "timestamp": entry["timestamp"],
            "file_path": str(file_path) if file_path else None,
            "file_size": file_size,
        })
        if len(results) >= limit:
            break
    return results


# ── JSONL Parser ───────────────────────────────────────────────────────────

def parse_session(file_path):
    """Parse a session JSONL file into structured analysis data.

    Returns a dict with:
      - turns: list of turn dicts
      - compactions: list of compaction events
      - tool_results: list of tool result size records
      - sidechain_count: number of sidechain messages
      - session_info: basic session metadata
    """
    file_path = Path(file_path)
    # ファイル名から取得したセッション ID をフォールバックに使う
    file_session_id = file_path.stem

    messages = []
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            messages.append(obj)

    turns = []
    compactions = []
    tool_results_all = []
    sidechain_count = 0
    session_id = None
    project_path = None
    first_ts = None
    last_ts = None
    models_used = set()

    # tool_use_id -> tool_name mapping (from assistant messages)
    tool_use_map = {}

    # Build turns from assistant messages with usage data
    prev_context = None
    current_turn = None

    for msg in messages:
        ts_str = msg.get("timestamp", "")
        msg_type = msg.get("type", "")

        if not session_id:
            session_id = msg.get("sessionId")
        if not project_path:
            project_path = msg.get("cwd")

        if ts_str and isinstance(ts_str, str):
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if first_ts is None or ts < first_ts:
                    first_ts = ts
                if last_ts is None or ts > last_ts:
                    last_ts = ts
            except (ValueError, TypeError):
                pass

        # Count sidechain messages
        if msg.get("isSidechain"):
            sidechain_count += 1
            continue

        # Compaction detection
        if msg_type == "system" and msg.get("subtype") == "compact_boundary":
            metadata = msg.get("compactMetadata", {})
            compactions.append({
                "timestamp": ts_str,
                "trigger": metadata.get("trigger", "unknown"),
                "pre_tokens": metadata.get("preTokens", 0),
            })
            continue

        # Extract tool_use blocks from assistant messages (for name mapping)
        if msg_type == "assistant":
            inner = msg.get("message", {})
            content = inner.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_use_map[block.get("id", "")] = block.get("name", "unknown")

        # Extract tool_result blocks from user messages
        if msg_type == "user":
            inner = msg.get("message", {})
            content = inner.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_id = block.get("tool_use_id", "")
                        tool_name = tool_use_map.get(tool_id, "unknown")
                        result_content = block.get("content", "")
                        if isinstance(result_content, list):
                            size = sum(len(json.dumps(item, ensure_ascii=False)) for item in result_content)
                        elif isinstance(result_content, str):
                            size = len(result_content)
                        else:
                            size = len(str(result_content))
                        tool_results_all.append({
                            "tool_use_id": tool_id,
                            "tool_name": tool_name,
                            "size_bytes": size,
                            "timestamp": ts_str,
                        })

        # Build turns from assistant messages with usage
        if msg_type == "assistant":
            inner = msg.get("message", {})
            usage = inner.get("usage", {})
            model = inner.get("model", "")

            if model and not model.startswith("<"):
                models_used.add(model)

            input_tokens = usage.get("input_tokens", 0)
            cache_read = usage.get("cache_read_input_tokens", 0)
            cache_creation = usage.get("cache_creation_input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            context_tokens = input_tokens + cache_read + cache_creation

            if context_tokens == 0:
                continue

            cost = calc_cost(model, usage) if model else 0.0

            # 同一 API コール（ストリーミング/リトライ）の判定:
            # context_tokens が同一 かつ タイムスタンプが 5 秒以内
            is_same_call = context_tokens == prev_context and current_turn is not None
            if is_same_call and ts_str and current_turn:
                try:
                    curr_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    prev_dt = datetime.fromisoformat(current_turn["timestamp"].replace("Z", "+00:00"))
                    if abs((curr_dt - prev_dt).total_seconds()) > 5:
                        is_same_call = False
                except (ValueError, TypeError):
                    pass

            if not is_same_call:
                # New turn
                current_turn = {
                    "turn_number": len(turns) + 1,
                    "timestamp": ts_str,
                    "model": model,
                    "context_tokens": context_tokens,
                    "input_tokens": input_tokens,
                    "cache_read": cache_read,
                    "cache_creation": cache_creation,
                    "output_tokens": output_tokens,
                    "cost": cost,
                    "delta_context": context_tokens - prev_context if prev_context is not None else 0,
                    "tool_results": [],  # populated later
                }
                turns.append(current_turn)
                prev_context = context_tokens
            else:
                # Same API call (streaming/retry), accumulate output
                current_turn["output_tokens"] += output_tokens
                current_turn["cost"] += cost

    # Associate tool_results with turns by timestamp proximity
    _associate_tool_results_with_turns(turns, tool_results_all)

    # Calculate cumulative cost
    cumulative_cost = 0.0
    for turn in turns:
        cumulative_cost += turn["cost"]
        turn["cumulative_cost"] = cumulative_cost

    return {
        "turns": turns,
        "compactions": compactions,
        "tool_results": tool_results_all,
        "sidechain_count": sidechain_count,
        "session_info": {
            "session_id": file_session_id,
            "project": project_path,
            "display_name": project_display_name(project_path),
            "first_ts": first_ts.isoformat() if first_ts else None,
            "last_ts": last_ts.isoformat() if last_ts else None,
            "duration_minutes": (last_ts - first_ts).total_seconds() / 60 if first_ts and last_ts else 0,
            "models": sorted(models_used),
        },
    }


def _associate_tool_results_with_turns(turns, tool_results):
    """Associate tool results with the turn that follows them (by timestamp)."""
    if not turns or not tool_results:
        return

    turn_timestamps = []
    for t in turns:
        ts_str = t.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            ts = datetime.min.replace(tzinfo=timezone.utc)
        turn_timestamps.append(ts)

    for tr in tool_results:
        ts_str = tr.get("timestamp", "")
        try:
            tr_ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue

        idx = bisect.bisect_left(turn_timestamps, tr_ts)
        if idx >= len(turns):
            idx = len(turns) - 1
        turns[idx]["tool_results"].append(tr)


# ── Analysis ───────────────────────────────────────────────────────────────

def analyze_context_growth(data, top_n=10):
    """Analyze context growth and identify biggest contributors."""
    turns = data["turns"]
    tool_results = data["tool_results"]

    # Top N turns by delta_context
    top_delta_turns = sorted(turns, key=lambda t: t["delta_context"], reverse=True)[:top_n]

    # Tool result size aggregation by tool name
    tool_stats = defaultdict(lambda: {"count": 0, "total_bytes": 0, "max_bytes": 0})
    for tr in tool_results:
        name = tr["tool_name"]
        size = tr["size_bytes"]
        tool_stats[name]["count"] += 1
        tool_stats[name]["total_bytes"] += size
        tool_stats[name]["max_bytes"] = max(tool_stats[name]["max_bytes"], size)

    for name, stats in tool_stats.items():
        stats["avg_bytes"] = stats["total_bytes"] / stats["count"] if stats["count"] else 0

    tool_ranking = sorted(tool_stats.items(), key=lambda x: x[1]["total_bytes"], reverse=True)

    return {
        "top_delta_turns": top_delta_turns,
        "tool_ranking": tool_ranking[:top_n],
    }


def generate_recommendations(data, analysis):
    """Generate rule-based recommendations."""
    recs = []
    tool_ranking = dict(analysis["tool_ranking"])

    if "Read" in tool_ranking:
        stats = tool_ranking["Read"]
        if stats["max_bytes"] > 50000:
            recs.append(
                "Read ツールの最大結果が {max_kb:.0f}KB あります。offset/limit パラメータを使って"
                "必要な行だけ読み込むことでコンテキスト消費を削減できます。".format(
                    max_kb=stats["max_bytes"] / 1024
                )
            )

    if "Bash" in tool_ranking:
        stats = tool_ranking["Bash"]
        if stats["max_bytes"] > 30000:
            recs.append(
                "Bash 出力の最大結果が {max_kb:.0f}KB あります。| head, | tail, | grep 等で"
                "出力を絞ることでコンテキスト消費を削減できます。".format(
                    max_kb=stats["max_bytes"] / 1024
                )
            )

    if "Grep" in tool_ranking:
        stats = tool_ranking["Grep"]
        if stats["max_bytes"] > 30000:
            recs.append(
                "Grep 結果の最大が {max_kb:.0f}KB です。glob やパスの絞り込み、"
                "head_limit の活用で結果量を制限できます。".format(
                    max_kb=stats["max_bytes"] / 1024
                )
            )

    if "Agent" in tool_ranking:
        stats = tool_ranking["Agent"]
        if stats["count"] > 5:
            recs.append(
                "Agent ツールが {count} 回使用されています。Agent の結果はメインコンテキストに"
                "戻されるため、頻繁な使用はコンテキストを膨張させます。".format(
                    count=stats["count"]
                )
            )

    if "WebFetch" in tool_ranking:
        stats = tool_ranking["WebFetch"]
        if stats["max_bytes"] > 50000:
            recs.append(
                "WebFetch の最大結果が {max_kb:.0f}KB です。プロンプトで必要な情報だけ"
                "抽出するよう指示すると結果サイズを削減できます。".format(
                    max_kb=stats["max_bytes"] / 1024
                )
            )

    compactions = data["compactions"]
    if len(compactions) >= 3:
        recs.append(
            "コンパクションが {count} 回発生しています。タスクを分割して"
            "セッションを短く保つことを検討してください。".format(count=len(compactions))
        )

    turns = data["turns"]
    if turns:
        max_ctx = max(t["context_tokens"] for t in turns)
        if max_ctx > 150000:
            recs.append(
                "最大コンテキストが {max_k:.0f}K トークンに達しています。"
                "大きなファイルの全体読み込みを避け、必要な部分だけ参照してください。".format(
                    max_k=max_ctx / 1000
                )
            )

    if not recs:
        recs.append("特に問題は検出されませんでした。")

    return recs


# ── Output Formatting ──────────────────────────────────────────────────────

def format_bytes(n):
    """Format byte count as human-readable string."""
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f}KB"
    return f"{n / (1024 * 1024):.1f}MB"


def format_tokens(n):
    """Format token count as human-readable string."""
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{n / 1000:.1f}K"
    return f"{n / 1_000_000:.2f}M"


def format_timestamp(ts_str):
    """Format ISO timestamp to concise local time."""
    if not ts_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return ts_str[:19]


def format_duration(minutes):
    """Format duration in minutes to human-readable string."""
    if minutes < 1:
        return "< 1分"
    if minutes < 60:
        return f"{minutes:.0f}分"
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    return f"{hours}時間{mins}分"


def render_ascii_chart(turns, compactions, terminal_width=None):
    """Render ASCII chart of context token consumption over turns."""
    if not turns:
        return "  (データなし)"

    if terminal_width is None:
        terminal_width = shutil.get_terminal_size((80, 24)).columns

    # Reserve space for labels
    label_width = 8  # "999.9K |"
    chart_width = max(terminal_width - label_width - 2, 20)

    max_tokens = max(t["context_tokens"] for t in turns)
    if max_tokens == 0:
        return "  (コンテキストトークンが 0)"

    # Compaction turn indices (approximate by timestamp)
    compaction_turns = set()
    for comp in compactions:
        comp_ts = comp.get("timestamp", "")
        if not comp_ts:
            continue
        try:
            comp_dt = datetime.fromisoformat(comp_ts.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        # Find the closest turn
        best_idx = 0
        best_diff = float("inf")
        for i, t in enumerate(turns):
            try:
                t_dt = datetime.fromisoformat(t["timestamp"].replace("Z", "+00:00"))
                diff = abs((t_dt - comp_dt).total_seconds())
                if diff < best_diff:
                    best_diff = diff
                    best_idx = i
            except (ValueError, TypeError):
                pass
        compaction_turns.add(best_idx)

    lines = []

    # If too many turns, downsample
    if len(turns) > chart_width:
        step = len(turns) / chart_width
        sampled_indices = [int(i * step) for i in range(chart_width)]
        display_turns = [(idx, turns[idx]) for idx in sampled_indices]
    else:
        display_turns = list(enumerate(turns))

    for idx, turn in display_turns:
        tokens = turn["context_tokens"]
        bar_len = int(tokens / max_tokens * chart_width)
        bar_len = max(bar_len, 1)  # at least 1 char

        label = f"{format_tokens(tokens):>6s} |"
        marker = "C" if idx in compaction_turns else "█"
        bar = marker * bar_len if idx in compaction_turns else "█" * bar_len

        lines.append(f"{label}{bar}")

    # Add axis
    lines.append(f"{'':>{label_width}}" + "└" + "─" * chart_width)
    lines.append(f"{'':>{label_width}} Turn 1{' ' * (chart_width - 10)}Turn {len(turns)}")

    return "\n".join(lines)


def render_text_report(data, analysis, top_n=10, show_chart=True):
    """Render a full text report."""
    info = data["session_info"]
    turns = data["turns"]
    compactions = data["compactions"]
    sidechain = data["sidechain_count"]

    lines = []

    # ── 1. Session Overview ──
    lines.append("=" * 70)
    lines.append("  コンテキスト消費分析レポート")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"  セッション ID : {info['session_id']}")
    lines.append(f"  プロジェクト   : {info['display_name']}")
    lines.append(f"  期間          : {info['first_ts'] or 'N/A'}")
    lines.append(f"                  → {info['last_ts'] or 'N/A'}")
    lines.append(f"                  ({format_duration(info['duration_minutes'])})")
    lines.append(f"  モデル        : {', '.join(get_model_display(m) for m in info['models']) or 'N/A'}")
    lines.append(f"  ターン数      : {len(turns)}")

    if turns:
        max_ctx = max(t["context_tokens"] for t in turns)
        total_cost = turns[-1].get("cumulative_cost", 0) if turns else 0
        lines.append(f"  最大コンテキスト : {format_tokens(max_ctx)} tokens")
        lines.append(f"  合計コスト    : ${total_cost:.4f}")

    lines.append(f"  コンパクション : {len(compactions)} 回")
    if sidechain:
        lines.append(f"  サイドチェーン : {sidechain} メッセージ")
    lines.append("")

    # ── 2. Context Progression Chart ──
    if show_chart:
        lines.append("─" * 70)
        lines.append("  コンテキスト推移 (C=コンパクション)")
        lines.append("─" * 70)
        lines.append(render_ascii_chart(turns, compactions))
        lines.append("")

    # ── 3. Compaction Events ──
    if compactions:
        lines.append("─" * 70)
        lines.append("  コンパクションイベント")
        lines.append("─" * 70)
        for i, comp in enumerate(compactions, 1):
            ts = format_timestamp(comp["timestamp"])
            pre = format_tokens(comp["pre_tokens"]) if comp["pre_tokens"] else "N/A"
            trigger = comp["trigger"]
            lines.append(f"  [{i}] {ts}  trigger={trigger}  pre_tokens={pre}")

            # Find post-compaction context
            comp_ts = comp.get("timestamp", "")
            if comp_ts:
                try:
                    comp_dt = datetime.fromisoformat(comp_ts.replace("Z", "+00:00"))
                    for turn in turns:
                        try:
                            t_dt = datetime.fromisoformat(turn["timestamp"].replace("Z", "+00:00"))
                            if t_dt > comp_dt:
                                reduction = comp["pre_tokens"] - turn["context_tokens"]
                                post_str = f"       → post_tokens={format_tokens(turn['context_tokens'])}"
                                if comp["pre_tokens"] > 0 and reduction > 0:
                                    post_str += f"  (削減: {format_tokens(reduction)})"
                                lines.append(post_str)
                                break
                        except (ValueError, TypeError):
                            pass
                except (ValueError, TypeError):
                    pass
        lines.append("")

    # ── 4. Top N Context Growth Turns ──
    top_turns = analysis["top_delta_turns"]
    if top_turns:
        lines.append("─" * 70)
        lines.append(f"  コンテキスト増加 Top {min(top_n, len(top_turns))}")
        lines.append("─" * 70)
        lines.append(f"  {'#':>3s}  {'時刻':8s}  {'Delta':>8s}  {'Context':>8s}  {'原因'}")
        lines.append(f"  {'─'*3}  {'─'*8}  {'─'*8}  {'─'*8}  {'─'*30}")

        for i, turn in enumerate(top_turns[:top_n], 1):
            ts = format_timestamp(turn["timestamp"])
            delta = format_tokens(turn["delta_context"])
            ctx = format_tokens(turn["context_tokens"])

            # Identify cause from tool results in this turn
            if turn["tool_results"]:
                biggest = max(turn["tool_results"], key=lambda x: x["size_bytes"])
                cause = f"{biggest['tool_name']} ({format_bytes(biggest['size_bytes'])})"
                if len(turn["tool_results"]) > 1:
                    cause += f" +{len(turn['tool_results'])-1} tools"
            else:
                cause = "(ユーザー入力 or システム)"

            lines.append(f"  {i:3d}  {ts:8s}  {delta:>8s}  {ctx:>8s}  {cause}")
        lines.append("")

    # ── 5. Tool Result Size Ranking ──
    tool_ranking = analysis["tool_ranking"]
    if tool_ranking:
        lines.append("─" * 70)
        lines.append("  ツール結果サイズランキング")
        lines.append("─" * 70)
        lines.append(f"  {'ツール名':<20s}  {'回数':>5s}  {'合計':>8s}  {'平均':>8s}  {'最大':>8s}")
        lines.append(f"  {'─'*20}  {'─'*5}  {'─'*8}  {'─'*8}  {'─'*8}")
        for name, stats in tool_ranking:
            lines.append(
                f"  {name:<20s}  {stats['count']:>5d}  "
                f"{format_bytes(stats['total_bytes']):>8s}  "
                f"{format_bytes(int(stats['avg_bytes'])):>8s}  "
                f"{format_bytes(stats['max_bytes']):>8s}"
            )
        lines.append("")

    # ── 6. Recommendations ──
    recs = generate_recommendations(data, analysis)
    lines.append("─" * 70)
    lines.append("  推奨事項")
    lines.append("─" * 70)
    for i, rec in enumerate(recs, 1):
        lines.append(f"  {i}. {rec}")
    lines.append("")
    lines.append("=" * 70)

    return "\n".join(lines)


def render_json_report(data, analysis, top_n=10):
    """Render analysis as JSON."""
    info = data["session_info"]
    turns = data["turns"]
    compactions = data["compactions"]

    # Simplify turns for JSON output (remove tool_results detail)
    simplified_turns = []
    for t in turns:
        simplified_turns.append({
            "turn_number": t["turn_number"],
            "timestamp": t["timestamp"],
            "model": t["model"],
            "context_tokens": t["context_tokens"],
            "delta_context": t["delta_context"],
            "input_tokens": t["input_tokens"],
            "cache_read": t["cache_read"],
            "cache_creation": t["cache_creation"],
            "output_tokens": t["output_tokens"],
            "cost": round(t["cost"], 6),
            "cumulative_cost": round(t.get("cumulative_cost", 0), 6),
            "tool_results_count": len(t["tool_results"]),
            "tool_results_total_bytes": sum(tr["size_bytes"] for tr in t["tool_results"]),
        })

    output = {
        "session_info": info,
        "summary": {
            "total_turns": len(turns),
            "max_context_tokens": max((t["context_tokens"] for t in turns), default=0),
            "total_cost": round(sum(t["cost"] for t in turns), 6),
            "compaction_count": len(compactions),
            "sidechain_messages": data["sidechain_count"],
        },
        "turns": simplified_turns,
        "compactions": compactions,
        "top_context_growth": [
            {
                "turn_number": t["turn_number"],
                "delta_context": t["delta_context"],
                "context_tokens": t["context_tokens"],
                "timestamp": t["timestamp"],
            }
            for t in analysis["top_delta_turns"][:top_n]
        ],
        "tool_ranking": [
            {"tool": name, **stats}
            for name, stats in analysis["tool_ranking"]
        ],
        "recommendations": generate_recommendations(data, analysis),
    }

    return json.dumps(output, indent=2, ensure_ascii=False)


# ── Session List Display ───────────────────────────────────────────────────

def _print_session_table(sessions):
    """Print formatted session table."""
    print("─" * 70)
    print("  最近のセッション一覧")
    print("─" * 70)
    print(f"  {'#':>3s}  {'日時':<20s}  {'プロジェクト':<25s}  {'サイズ':>8s}  {'ID'}")
    print(f"  {'─'*3}  {'─'*20}  {'─'*25}  {'─'*8}  {'─'*8}")

    for i, s in enumerate(sessions, 1):
        ts = datetime.fromtimestamp(s["timestamp"] / 1000).strftime("%Y-%m-%d %H:%M") if s["timestamp"] else "N/A"
        proj = s["display_name"][:25]
        size = format_bytes(s["file_size"]) if s["file_size"] else "N/A"
        sid_short = s["sessionId"][:8]
        print(f"  {i:3d}  {ts:<20s}  {proj:<25s}  {size:>8s}  {sid_short}")


def display_session_list(sessions, interactive=True):
    """Display formatted session list and optionally prompt for selection.

    Returns selected session ID or None.
    """
    if not sessions:
        print("セッションが見つかりませんでした。")
        return None

    _print_session_table(sessions)

    if not interactive:
        return None

    print("")
    print("番号を入力してセッションを選択 (q で終了): ", end="", flush=True)

    try:
        choice = input().strip()
    except (EOFError, KeyboardInterrupt):
        return None

    if choice.lower() == "q" or not choice:
        return None

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(sessions):
            return sessions[idx]["sessionId"]
    except ValueError:
        pass

    print(f"無効な入力: {choice}")
    return None


# ── CLI Entry Point ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Claude Code セッションのコンテキスト消費パターンを分析する",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""使用例:
  python analyze_context.py -l                  # セッション一覧
  python analyze_context.py -l -p trade         # プロジェクト名でフィルタ
  python analyze_context.py 0342bc92            # 短縮 ID で分析
  python analyze_context.py SESSION_ID --json   # JSON 出力
""",
    )
    parser.add_argument(
        "session_id", nargs="?", default=None,
        help="セッション ID（UUID）またはスラッグ（前方一致）",
    )
    parser.add_argument(
        "-l", "--list", action="store_true",
        help="最近のセッション一覧を表示",
    )
    parser.add_argument(
        "-p", "--project", default=None,
        help="プロジェクト名でフィルタ（部分一致）",
    )
    parser.add_argument(
        "-n", "--top", type=int, default=10,
        help="ランキング表示件数（デフォルト: 10）",
    )
    parser.add_argument(
        "--no-chart", action="store_true",
        help="ASCII チャートを省略",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="JSON 形式で出力",
    )

    args = parser.parse_args()

    # List mode (non-interactive) or piped input
    if args.list or (args.session_id is None and not sys.stdin.isatty()):
        sessions = list_recent_sessions(project_filter=args.project)
        display_session_list(sessions, interactive=False)
        return

    if args.session_id is None:
        sessions = list_recent_sessions(project_filter=args.project)
        selected = display_session_list(sessions)
        if not selected:
            return
        args.session_id = selected

    # Find session file
    file_path, matched_id = find_session_file(args.session_id)
    if not file_path:
        print(f"セッションが見つかりません: {args.session_id}")
        sys.exit(1)

    if not file_path.exists():
        print(f"ファイルが存在しません: {file_path}")
        sys.exit(1)

    # Parse and analyze
    data = parse_session(file_path)
    analysis = analyze_context_growth(data, top_n=args.top)

    # Output
    if args.json_output:
        print(render_json_report(data, analysis, top_n=args.top))
    else:
        print(render_text_report(data, analysis, top_n=args.top, show_chart=not args.no_chart))


if __name__ == "__main__":
    main()
