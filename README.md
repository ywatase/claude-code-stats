# Claude Code Usage Statistics

A comprehensive analytics dashboard for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) usage data. Parses your local Claude Code session transcripts, calculates hypothetical API costs, and generates an interactive HTML dashboard.

***Disclaimer:*** *This is an unofficial, community-built tool. Not affiliated with or endorsed by Anthropic.*

## Features

- **KPI Dashboard** -- Total API-equivalent cost, messages, sessions, output tokens
- **Token & API Value** -- Daily costs, cumulative costs, model distribution
- **Activity** -- Message patterns, hourly distribution, weekday distribution
- **Projects** -- Top projects by cost, detailed project metrics
- **Sessions** -- Filterable/searchable session details with expandable metadata
- **Plan & Billing** -- Cost savings analysis vs. your subscription plan
- **Insights** -- Tool usage, storage breakdown, plugins, todos, file snapshots

![Dashboard Screenshot](docs/images/claude-code-stats-01.png)

## Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/AeternaLabsHQ/claude-code-stats.git
   cd claude-code-stats
   ```

2. **Create your configuration**
   ```bash
   cp config.example.json config.json
   ```
   Edit `config.json` to match your subscription plan and preferences.

3. **Run the extractor**
   ```bash
   python3 extract_stats.py
   ```

4. **Open the dashboard**
   ```bash
   open public/dashboard.html      # macOS
   xdg-open public/dashboard.html  # Linux
   start public/dashboard.html     # Windows
   ```

## Configuration

See [`config.example.json`](config.example.json) for all options:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `language` | `string` | `"en"` | UI language (`"en"` or `"de"`) |
| `plan_history` | `array` | `[]` | Your subscription plan history |
| `migration.enabled` | `bool` | `false` | Enable data from a migration backup |
| `migration.dir` | `string` | `null` | Path to migration backup directory |

### Plan History

Each entry in `plan_history` represents a subscription period:

```json
{
  "plan": "Max",
  "start": "2026-01-23",
  "end": null,
  "cost_eur": 87.61,
  "cost_usd": 93.00,
  "billing_day": 23
}
```

- `end: null` means the plan is currently active
- `billing_day` determines billing cycle boundaries for cost analysis

### Migration Support

If you migrated Claude Code data from another machine, you can include that historical data:

```json
{
  "migration": {
    "enabled": true,
    "dir": "~/backups/old-machine",
    "claude_dir_name": ".claude-windows",
    "dot_claude_json_name": ".claude-windows.json"
  }
}
```

The script deduplicates sessions across both sources automatically.

## Output

The script generates files in the `public/` directory:

- `dashboard.html` -- Self-contained interactive dashboard (open in any browser)
- `dashboard_data.json` -- Raw aggregated data (for custom analysis)

## Context Consumption Analyzer

`analyze_context.py` is a standalone CLI tool that analyzes context consumption patterns of a specific Claude Code session. It helps identify what causes context growth and compaction (context compression) events.

### Usage

```bash
# List recent sessions
python3 analyze_context.py -l

# Filter sessions by project name
python3 analyze_context.py -l -p myproject

# Analyze a session by ID (prefix match supported)
python3 analyze_context.py 0342bc92

# Output as JSON
python3 analyze_context.py SESSION_ID --json

# Skip ASCII chart
python3 analyze_context.py SESSION_ID --no-chart
```

### Report Contents

- **Session overview** -- Duration, model, max context tokens, total cost, compaction count
- **Context progression chart** -- ASCII visualization of context token growth over turns (C = compaction)
- **Compaction events** -- Timestamp, trigger, pre/post token counts
- **Top context growth turns** -- Which turns consumed the most context and why
- **Tool result size ranking** -- Which tools returned the largest results
- **Recommendations** -- Actionable suggestions to reduce context consumption

## Automation

To auto-refresh the dashboard periodically:

```bash
*/10 * * * * cd /path/to/claude-stats && python3 extract_stats.py 2>&1 >> update.log
```

## Requirements

- Python 3.8+
- No external dependencies (stdlib only)
- Claude Code installed with session data in `~/.claude/`

## Localization

The dashboard supports English and German. Set `"language": "en"` or `"language": "de"` in your `config.json`.

To add a new language, create a file in `locales/` following the structure of [`locales/en.json`](locales/en.json).

## License

MIT
