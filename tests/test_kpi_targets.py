"""KPI targets: config seam with defaults for every key."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from claudestats_core import settings  # noqa: E402
from claudestats_core.settings import normalize_kpi_targets  # noqa: E402

DEFAULTS = {
    "monthly_ai_duration_hours": 160,
    "monthly_cost_jpy": 100000,
    "usd_to_jpy": 150,
}


class NormalizeKpiTargetsTest(unittest.TestCase):
    def test_none_yields_defaults(self):
        self.assertEqual(normalize_kpi_targets(None), DEFAULTS)

    def test_empty_dict_yields_defaults(self):
        self.assertEqual(normalize_kpi_targets({}), DEFAULTS)

    def test_partial_config_fills_the_rest(self):
        got = normalize_kpi_targets({"usd_to_jpy": 160})
        self.assertEqual(got["usd_to_jpy"], 160)
        self.assertEqual(got["monthly_ai_duration_hours"], 160)
        self.assertEqual(got["monthly_cost_jpy"], 100000)

    def test_unknown_keys_are_dropped(self):
        self.assertEqual(set(normalize_kpi_targets({"bogus": 1})), set(DEFAULTS))

    def test_result_is_a_fresh_dict(self):
        # settings.configure() stores references, so a shared dict would let a
        # later caller mutate the defaults for everyone.
        a = normalize_kpi_targets(None)
        a["usd_to_jpy"] = 999
        self.assertEqual(normalize_kpi_targets(None)["usd_to_jpy"], 150)


class SettingsSeamTest(unittest.TestCase):
    def tearDown(self):
        settings.configure(kpi_targets=dict(DEFAULTS))

    def test_kpi_targets_is_a_known_setting(self):
        settings.configure(kpi_targets={"usd_to_jpy": 170})
        self.assertEqual(settings.KPI_TARGETS["usd_to_jpy"], 170)

    def test_default_is_usable_without_configure(self):
        self.assertEqual(set(settings.KPI_TARGETS), set(DEFAULTS))


class ConfigExampleTest(unittest.TestCase):
    def test_example_config_documents_every_key(self):
        cfg = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
        self.assertEqual(set(cfg["kpi_targets"]), set(DEFAULTS))


class DashboardDataTest(unittest.TestCase):
    def test_targets_reach_the_page(self):
        from tests.fixture_utils import (
            assistant_line,
            patched_sources,
            user_line,
            write_jsonl,
        )
        import tempfile

        tmp = Path(tempfile.mkdtemp(prefix="cs-kpitgt-"))
        pd = tmp / "projects"
        write_jsonl(pd / "proj1" / "S1.jsonl", [user_line(), assistant_line()])
        saved = dict(settings.KPI_TARGETS)
        settings.configure(kpi_targets=normalize_kpi_targets({"usd_to_jpy": 175}))
        try:
            with patched_sources(pd) as es:
                data = es.build_dashboard_data(
                    es.parse_session_transcripts(), {}, {}, []
                )
        finally:
            settings.configure(kpi_targets=saved)
        self.assertEqual(set(data["kpi_targets"]), set(DEFAULTS))
        self.assertEqual(data["kpi_targets"]["usd_to_jpy"], 175)


if __name__ == "__main__":
    unittest.main()
