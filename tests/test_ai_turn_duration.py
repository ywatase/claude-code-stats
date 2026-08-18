"""AI turn duration: user -> assistant round-trips, capped per turn."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from claudestats_core.sessions import (  # noqa: E402
    calc_ai_turn_duration,
    calc_ai_turn_duration_by_day,
)

from tests.fixture_utils import (  # noqa: E402
    assistant_line,
    patched_sources,
    user_line,
    write_jsonl,
)

MIN = 60_000
DAY = 24 * 60 * MIN


class CalcAiTurnDurationTest(unittest.TestCase):
    def test_empty_is_zero(self):
        self.assertEqual(calc_ai_turn_duration([]), 0)

    def test_single_pair_is_the_gap(self):
        pairs = [("user", 0), ("assistant", 2 * MIN)]
        self.assertEqual(calc_ai_turn_duration(pairs), 2 * MIN)

    def test_consecutive_pairs_accumulate(self):
        pairs = [
            ("user", 0),
            ("assistant", 2 * MIN),
            ("user", 10 * MIN),
            ("assistant", 13 * MIN),
        ]
        self.assertEqual(calc_ai_turn_duration(pairs), 5 * MIN)

    def test_gap_of_30_minutes_or_more_is_dropped_as_idle(self):
        # The user walked away; this is not AI working time.
        pairs = [("user", 0), ("assistant", 30 * MIN)]
        self.assertEqual(calc_ai_turn_duration(pairs), 0)

    def test_assistant_without_a_preceding_user_is_ignored(self):
        pairs = [("assistant", 5 * MIN), ("assistant", 6 * MIN)]
        self.assertEqual(calc_ai_turn_duration(pairs), 0)

    def test_only_the_latest_user_message_opens_the_turn(self):
        # Two prompts in a row: the turn starts at the second one.
        pairs = [("user", 0), ("user", 4 * MIN), ("assistant", 5 * MIN)]
        self.assertEqual(calc_ai_turn_duration(pairs), 1 * MIN)

    def test_one_assistant_closes_only_one_turn(self):
        pairs = [("user", 0), ("assistant", MIN), ("assistant", 9 * MIN)]
        self.assertEqual(calc_ai_turn_duration(pairs), MIN)

    def test_non_positive_gap_is_dropped(self):
        # Out-of-order timestamps happen in merged transcripts.
        pairs = [("user", 5 * MIN), ("assistant", 5 * MIN)]
        self.assertEqual(calc_ai_turn_duration(pairs), 0)


class ByDayTest(unittest.TestCase):
    """Multi-day sessions feed the daily charts through per_day slices."""

    def test_empty_is_an_empty_dict(self):
        self.assertEqual(calc_ai_turn_duration_by_day([]), {})

    def test_turn_lands_on_the_day_it_started(self):
        # Attribution matches daily_message_count, which keys off the prompt.
        pairs = [("user", DAY - MIN), ("assistant", DAY + MIN)]
        got = calc_ai_turn_duration_by_day(pairs)
        self.assertEqual(got, {"1970-01-01": 2 * MIN})

    def test_days_are_kept_separate(self):
        pairs = [
            ("user", 0),
            ("assistant", MIN),
            ("user", 2 * DAY),
            ("assistant", 2 * DAY + 3 * MIN),
        ]
        got = calc_ai_turn_duration_by_day(pairs)
        self.assertEqual(got, {"1970-01-01": MIN, "1970-01-03": 3 * MIN})

    def test_total_matches_the_scalar_function(self):
        pairs = [
            ("user", 0),
            ("assistant", MIN),
            ("user", DAY),
            ("assistant", DAY + 7 * MIN),
            ("user", 3 * DAY),
            ("assistant", 3 * DAY + 40 * MIN),
        ]  # dropped
        self.assertEqual(
            sum(calc_ai_turn_duration_by_day(pairs).values()),
            calc_ai_turn_duration(pairs),
        )

    def test_keys_are_iso_dates(self):
        got = calc_ai_turn_duration_by_day([("user", 0), ("assistant", MIN)])
        for key in got:
            self.assertRegex(key, r"^\d{4}-\d{2}-\d{2}$")


def _build(session_lines):
    tmp = Path(tempfile.mkdtemp(prefix="cs-aidur-"))
    pd = tmp / "projects"
    write_jsonl(pd / "proj1" / "S1.jsonl", session_lines)
    with patched_sources(pd) as es:
        sessions = es.parse_session_transcripts()
        return es.build_dashboard_data(sessions, {}, {}, [])


class DashboardWiringTest(unittest.TestCase):
    """The metric has to survive the trip through build_dashboard_data."""

    LINES = [
        user_line(ts="2026-06-10T10:00:00Z"),
        assistant_line(msg_id="m1", ts="2026-06-10T10:02:00Z"),
        user_line(ts="2026-06-10T23:59:00Z", text="second"),
        assistant_line(msg_id="m2", ts="2026-06-11T00:03:00Z"),
        user_line(ts="2026-06-11T09:00:00Z", text="third"),
        assistant_line(msg_id="m3", ts="2026-06-11T09:01:00Z"),
    ]

    def setUp(self):
        self.data = _build(self.LINES)
        self.sessions = self.data["sessions"]

    def test_every_session_carries_the_metric(self):
        for s in self.sessions:
            self.assertIn("ai_duration_min", s)

    def test_kpi_total_matches_the_session_sum(self):
        want = round(sum(s["ai_duration_min"] for s in self.sessions) / 60, 2)
        self.assertEqual(self.data["kpi"]["total_ai_duration_hours"], want)

    def test_ai_time_never_exceeds_wall_clock(self):
        for s in self.sessions:
            self.assertLessEqual(s["ai_duration_min"], s["duration_min"] + 0.2,
                                 s["session_id"])

    def test_multi_day_per_day_slices_sum_to_the_session_total(self):
        multi = [s for s in self.sessions if s.get("per_day")]
        self.assertTrue(multi, "fixture should span two days")
        for s in multi:
            sliced = sum(v["ai_duration_min"] for v in s["per_day"].values())
            self.assertAlmostEqual(sliced, s["ai_duration_min"], delta=0.2,
                                   msg=s["session_id"])

    def test_a_midnight_crossing_turn_lands_on_its_prompt_day(self):
        s = next(x for x in self.sessions if x.get("per_day"))
        # 4 min turn started 23:59 on the 10th; 2 min + that = 6 min on day 1.
        self.assertAlmostEqual(s["per_day"]["2026-06-10"]["ai_duration_min"],
                               6.0, delta=0.2)
        self.assertAlmostEqual(s["per_day"]["2026-06-11"]["ai_duration_min"],
                               1.0, delta=0.2)

    def test_private_scratch_keys_do_not_reach_the_page(self):
        # session_list.append() builds an explicit dict, so these should never
        # serialize. This guards a future change that spreads sess wholesale.
        blob = json.dumps(self.data)
        self.assertNotIn("typed_timestamps", blob)
        self.assertNotIn("ai_turn_duration_ms_by_day", blob)


if __name__ == "__main__":
    unittest.main()
