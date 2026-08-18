"""KPI Goals tab: wiring between template, JS, and locales."""

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DASHBOARD_JS = (ROOT / "templates" / "dashboard.js").read_text(encoding="utf-8")
DASHBOARD_HTML = (ROOT / "templates" / "dashboard.html").read_text(encoding="utf-8")
DASHBOARD_CSS = (ROOT / "templates" / "dashboard.css").read_text(encoding="utf-8")
LOCALES = {
    p.stem: json.loads(p.read_text(encoding="utf-8"))
    for p in (ROOT / "locales").glob("*.json")
}

CANVAS_IDS = [
    "chartGoalsDailyDuration",
    "chartGoalsDailyCost",
    "chartGoalsWeeklyDuration",
    "chartGoalsWeeklyCost",
    "chartGoalsMonthlyTrend",
]
GOALS_KEYS = {
    "ai_duration",
    "token_cost",
    "target",
    "daily_avg",
    "remaining",
    "projected",
    "daily_duration",
    "daily_cost",
    "weekly_duration",
    "weekly_cost",
    "monthly_trend",
    "target_line",
    "on_track",
    "behind",
    "ahead",
}


def render_goals_body():
    """The full body of renderGoals(), or None if it cannot be isolated.

    The closing brace is matched at column 0, so a stray top-level "}" inside
    the function would truncate the capture. Callers assert the tail marker
    below so a truncated match fails loudly instead of silently passing.
    """
    m = re.search(r"function renderGoals\(\) \{\n(.*?)\n\}", DASHBOARD_JS, re.S)
    return m.group(1) if m else None


class TabRegistrationTest(unittest.TestCase):
    def test_goals_is_in_tab_names(self):
        block = re.search(r"const TAB_NAMES = \[(.*?)\];", DASHBOARD_JS, re.S)
        self.assertIsNotNone(block)
        self.assertIn("id:'goals'", block.group(1).replace(" ", ""))

    def test_tab_id_matches_the_alias_test_regex(self):
        # tests/test_tab_aliases.py scrapes ids with [a-z]+ only.
        block = re.search(r"const TAB_NAMES = \[(.*?)\];", DASHBOARD_JS, re.S)
        self.assertIn("goals", set(re.findall(r"id:\s*'([a-z]+)'", block.group(1))))

    def test_goals_is_last_so_the_default_tab_is_unchanged(self):
        # initTabs() and the #vcTabs IIFE both mark index 0 active.
        block = re.search(r"const TAB_NAMES = \[(.*?)\];", DASHBOARD_JS, re.S)
        ids = re.findall(r"id:\s*'([a-z]+)'", block.group(1))
        self.assertEqual(ids[-1], "goals")
        self.assertEqual(ids[0], "costs")

    def test_html_has_the_tab_content_container(self):
        self.assertIn('id="tab-goals"', DASHBOARD_HTML)

    def test_tab_content_is_not_active_by_default(self):
        section = re.search(r'<div class="([^"]*)" id="tab-goals"', DASHBOARD_HTML)
        self.assertIsNotNone(section)
        self.assertNotIn("active", section.group(1))

    def test_section_opens_with_the_shared_header_block(self):
        # Every sibling tab-content starts with .vc-tab-h; match the pattern.
        tail = DASHBOARD_HTML.split('id="tab-goals"', 1)[1][:400]
        self.assertIn("vc-tab-h", tail)
        self.assertIn("vc-tab-h-title", tail)


class RenderWiringTest(unittest.TestCase):
    def test_render_goals_is_defined(self):
        self.assertIn("function renderGoals(", DASHBOARD_JS)

    def test_render_goals_runs_on_initial_render_and_on_filter(self):
        # 3 hits minimum: the definition line, the boot call, the applyFilter
        # call. Anything less means one of the two call sites is missing.
        self.assertGreaterEqual(DASHBOARD_JS.count("renderGoals()"), 3)

    def test_filter_data_recomputes_the_ai_duration_total(self):
        # Without this, F.kpi.total_ai_duration_hours is undefined for every
        # filter but "All", and both cards silently read 0%.
        body = re.search(r"function filterData\((.*?)\n\}", DASHBOARD_JS, re.S)
        self.assertIsNotNone(body)
        self.assertIn("total_ai_duration_hours", body.group(1))

    def test_every_canvas_exists_in_the_template(self):
        for cid in CANVAS_IDS:
            self.assertIn(f'id="{cid}"', DASHBOARD_HTML, f"{cid} missing in HTML")
            self.assertIn(cid, DASHBOARD_JS, f"{cid} unused in JS")

    def test_progress_grid_container_exists(self):
        self.assertIn('id="goalsProgressGrid"', DASHBOARD_HTML)

    def test_the_captured_function_body_is_the_whole_function(self):
        # Guards every assertion below that greps this body.
        body = render_goals_body()
        self.assertIsNotNone(body, "renderGoals() not found")
        self.assertIn(
            "chartGoalsMonthlyTrend", body, "capture truncated before the last chart"
        )

    def test_no_hardcoded_hex_colors_in_render_goals(self):
        # Colors must come from the vc token helpers so both themes stay
        # correct; the ported implementation had ~15 hardcoded hexes.
        body = render_goals_body()
        self.assertEqual(re.findall(r"#[0-9a-fA-F]{6}\b", body), [])

    def test_chart_colors_come_from_the_vc_helpers(self):
        body = render_goals_body()
        self.assertTrue(
            "vcColor(" in body or "_vcLiveVar(" in body,
            "renderGoals must read live vc tokens so custom.css wins",
        )

    def test_styles_live_in_the_stylesheet(self):
        self.assertIn(".goals-card", DASHBOARD_CSS)

    def test_the_only_inline_style_is_the_computed_bar_width(self):
        # The progress bar's width is a runtime percentage and cannot live in
        # the stylesheet. Everything else -- and every color in particular --
        # must come from .goals-* classes so the theme switch reaches it.
        body = render_goals_body()
        for decl in re.findall(r"style=\\?\"([^\"\\]*)", body):
            self.assertTrue(
                decl.startswith("width:"), f"unexpected inline style: {decl!r}"
            )


class LocaleTest(unittest.TestCase):
    def test_every_locale_has_the_tab_label(self):
        for name, loc in LOCALES.items():
            self.assertIn("goals", loc["tabs"], f"{name}.json missing tabs.goals")

    def test_every_locale_has_the_full_goals_section(self):
        for name, loc in LOCALES.items():
            self.assertEqual(
                GOALS_KEYS - set(loc.get("goals", {})),
                set(),
                f"{name}.json is missing goals keys",
            )

    def test_locales_agree_on_key_sets(self):
        keysets = {name: set(loc["goals"]) for name, loc in LOCALES.items()}
        self.assertEqual(len(set(map(frozenset, keysets.values()))), 1, keysets)


if __name__ == "__main__":
    unittest.main()
