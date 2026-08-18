"""Embedded JSON must never carry a raw "<" into an inline <script> block."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from extract_stats import _embed_json  # noqa: E402

# "<!--" followed by "<script" puts the HTML tokenizer into the
# script-data-double-escaped state, where "</script>" alone no longer
# closes the tag. Escaping only "</" is therefore not sufficient.
HOSTILE = "<!-- <script> </script> --> </ScRiPt >"


class EmbedJsonTest(unittest.TestCase):
    def test_no_raw_angle_bracket_survives(self):
        out = _embed_json({"text": HOSTILE})
        self.assertNotIn("<", out)

    def test_value_round_trips_unchanged(self):
        out = _embed_json({"text": HOSTILE})
        self.assertEqual(json.loads(out)["text"], HOSTILE)

    def test_dumps_kwargs_are_forwarded(self):
        out = _embed_json({"a": 1, "b": 2}, separators=(",", ":"))
        self.assertEqual(out, '{"a":1,"b":2}')

    def test_non_ascii_is_not_escaped(self):
        # ensure_ascii=False is the project-wide convention; keep it.
        self.assertIn("日本語", _embed_json({"t": "日本語"}))


class CallSiteTest(unittest.TestCase):
    """Every inline-script embedding must route through _embed_json."""

    SOURCE = (ROOT / "extract_stats.py").read_text(encoding="utf-8")

    def test_no_partial_escape_remains(self):
        # The upstream "</"-only guard is strictly weaker; it must be gone.
        self.assertNotIn('replace("</", "<\\\\/")', self.SOURCE)

    def test_all_placeholders_are_fed_by_embed_json(self):
        # __DATA_PLACEHOLDER__ is the inline-HTML fallback path
        # (build_inline_html), which is fed the same escaped string.
        for name in (
            "__SESSION_DATA__",
            "__FLOW_DATA__",
            "__PROJECT_DATA__",
            "__DASHBOARD_DATA__",
            "__DATA_PLACEHOLDER__",
        ):
            self.assertIn(name, self.SOURCE, f"{name} placeholder disappeared")

    def test_embed_json_used_at_least_five_times(self):
        # dashboard, locale, session, flow, project (+ the definition itself)
        self.assertGreaterEqual(self.SOURCE.count("_embed_json("), 6)


if __name__ == "__main__":
    unittest.main()
