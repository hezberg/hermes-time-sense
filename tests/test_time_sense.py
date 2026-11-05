import importlib.util
import os
import sys
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timedelta, timezone

PLUGIN_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "__init__.py"
)
spec = importlib.util.spec_from_file_location("time_sense", PLUGIN_PATH)
ts = importlib.util.module_from_spec(spec)
sys.modules["time_sense"] = ts
spec.loader.exec_module(ts)

SH = timezone(timedelta(hours=8))


def dt(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=SH)


class FormatTests(unittest.TestCase):
    def test_stamp_weekday_is_code_computed(self):
        # 2026-11-05 is a Thursday (verified against the calendar).
        self.assertEqual(ts._format_stamp(dt(2026, 11, 5, 8, 15)), "2026-11-05 Thu 08:15")
        self.assertEqual(ts._format_stamp(dt(2026, 11, 4, 23, 40)), "2026-11-04 Wed 23:40")

    def test_elapsed_formats(self):
        self.assertEqual(ts._format_elapsed(timedelta(hours=8, minutes=35)), "8h35m")
        self.assertEqual(ts._format_elapsed(timedelta(days=2, hours=3, minutes=4)), "2d 3h04m")
        self.assertEqual(ts._format_elapsed(timedelta(minutes=12)), "12m")
        self.assertEqual(ts._format_elapsed(timedelta(hours=1, minutes=5, seconds=59)), "1h05m")


class ContextTests(unittest.TestCase):
    LABEL = "Asia/Shanghai"

    def test_no_prev_just_time_line(self):
        ctx = ts._build_context(dt(2026, 11, 5, 8, 15), self.LABEL, None, 3600)
        self.assertEqual(ctx, "[time] 2026-11-05 Thu 08:15 Asia/Shanghai")

    def test_short_gap_same_day_no_gap_line(self):
        now = dt(2026, 11, 5, 8, 15)
        prev = dt(2026, 11, 5, 8, 5)
        ctx = ts._build_context(now, self.LABEL, prev, 3600)
        self.assertNotIn("[time-gap]", ctx)

    def test_overnight_gap_line_with_new_day(self):
        now = dt(2026, 11, 5, 8, 15)
        prev = dt(2026, 11, 4, 23, 40)
        ctx = ts._build_context(now, self.LABEL, prev, 3600)
        self.assertIn(
            "[time-gap] Last human interaction was 2026-11-04 Wed 23:40, 8h35m ago. "
            "A new day has started.",
            ctx,
        )

    def test_long_gap_same_day_no_new_day_note(self):
        now = dt(2026, 11, 5, 15, 0)
        prev = dt(2026, 11, 5, 9, 0)
        ctx = ts._build_context(now, self.LABEL, prev, 3600)
        self.assertIn("6h00m ago.", ctx)
        self.assertNotIn("A new day", ctx)

    def test_day_change_under_threshold_still_flags(self):
        now = dt(2026, 11, 5, 0, 2)
        prev = dt(2026, 11, 4, 23, 59)
        ctx = ts._build_context(now, self.LABEL, prev, 3600)
        self.assertIn("[time-gap]", ctx)
        self.assertIn("A new day has started.", ctx)

    def test_clock_went_backwards_no_gap_line(self):
        now = dt(2026, 11, 5, 8, 0)
        prev = dt(2026, 11, 5, 9, 0)
        ctx = ts._build_context(now, self.LABEL, prev, 3600)
        self.assertNotIn("[time-gap]", ctx)


class StateTests(unittest.TestCase):
    def test_state_roundtrip_and_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "last_seen.json")
            self.assertIsNone(ts._load_prev(path))
            now = dt(2026, 11, 5, 8, 15)
            ts._save_now(now, path)
            self.assertEqual(ts._load_prev(path), now)
            # no temp files left behind by the atomic write
            self.assertEqual(os.listdir(tmp), ["last_seen.json"])

    def test_corrupt_state_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "last_seen.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("not json")
            self.assertIsNone(ts._load_prev(path))


class ClassificationTests(unittest.TestCase):
    def test_human_platforms(self):
        for kwargs in (
            {},
            {"platform": "cli"},
            {"platform": "feishu", "session_id": "s1", "sender_id": "u1"},
            {"platform": "telegram"},
            {"platform": ""},
        ):
            self.assertTrue(ts._is_human_turn(kwargs), kwargs)

    def test_cron_platform_is_machine(self):
        self.assertFalse(ts._is_human_turn({"platform": "cron"}))
        self.assertFalse(ts._is_human_turn({"platform": "Cron"}))

    def test_subagent_and_parent_are_machine(self):
        self.assertFalse(ts._is_human_turn({"platform": "subagent"}))
        self.assertFalse(
            ts._is_human_turn({"platform": "cli", "parent_session_id": "p1"})
        )

    def test_cron_session_id_is_machine(self):
        self.assertFalse(
            ts._is_human_turn(
                {"platform": "cli", "session_id": "cron_job42_20261105_075500"}
            )
        )

    def test_kanban_env_marker_is_machine(self):
        with mock.patch.dict(os.environ, {"HERMES_KANBAN_TASK": "t_1"}):
            self.assertFalse(ts._is_human_turn({"platform": "cli"}))
        self.assertTrue(ts._is_human_turn({"platform": "cli"}))


class OvernightCronScenarioTests(unittest.TestCase):
    """The reported bug: a 5-minute cron kept last_seen at 'just now',
    so the next morning's human turn saw a 5-minute gap, not overnight."""

    def test_cron_runs_do_not_move_human_clock(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "last_seen.json")
            nows = [
                (dt(2026, 11, 4, 23, 40), "Asia/Shanghai"),   # human, evening
                (dt(2026, 11, 4, 23, 45), "Asia/Shanghai"),   # cron
                (dt(2026, 11, 5, 7, 55), "Asia/Shanghai"),    # cron, next morning
                (dt(2026, 11, 5, 8, 15), "Asia/Shanghai"),    # human, next morning
            ]
            with mock.patch.object(ts, "_state_path", lambda: path), \
                 mock.patch.object(ts, "_resolve_now", side_effect=nows), \
                 mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("HERMES_KANBAN_TASK", None)

                evening = ts._pre_llm_call(platform="feishu", session_id="chat1")
                self.assertNotIn("[time-gap]", evening["context"])
                self.assertEqual(ts._load_prev(path), dt(2026, 11, 4, 23, 40))

                for _ in range(2):
                    cron = ts._pre_llm_call(
                        platform="cron", session_id="cron_zsxq_20261105_075500"
                    )
                    # cron gets its time line, no gap line, no state write
                    self.assertTrue(cron["context"].startswith("[time] "))
                    self.assertNotIn("[time-gap]", cron["context"])
                    self.assertEqual(ts._load_prev(path), dt(2026, 11, 4, 23, 40))

                morning = ts._pre_llm_call(platform="feishu", session_id="chat1")
                self.assertIn(
                    "Last human interaction was 2026-11-04 Wed 23:40, 8h35m ago. "
                    "A new day has started.",
                    morning["context"],
                )


class RegisterTests(unittest.TestCase):
    def test_register_registers_pre_llm_call(self):
        hooks = {}

        class Ctx:
            def register_hook(self, name, handler):
                hooks[name] = handler

        ts.register(Ctx())
        self.assertIn("pre_llm_call", hooks)
        self.assertIs(hooks["pre_llm_call"], ts._pre_llm_call)

    def test_hook_returns_context_dict(self):
        result = ts._pre_llm_call()
        self.assertIsInstance(result, dict)
        self.assertTrue(result["context"].startswith("[time] "))


if __name__ == "__main__":
    unittest.main()
