import contextlib
import io
import os
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import alarm


class AlarmTests(unittest.TestCase):
    def test_cli_rejects_invalid_input_before_audio(self):
        for args in ([], ["--at", "7:30"], ["--at", "24:00"],
                     ["--in", "0"], ["--in", "1441"], ["--in", "1.5"],
                     ["--at", "07:30", "--in", "5"]):
            with self.subTest(args=args), patch.object(alarm, "Audio") as audio:
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as exit_:
                        alarm.main(args)
                self.assertEqual(exit_.exception.code, 2)
                audio.assert_not_called()

    def test_resolves_today_tomorrow_and_year_rollover(self):
        if not hasattr(time, "tzset"):
            self.skipTest("tzset unavailable")
        previous = os.environ.get("TZ")
        try:
            os.environ["TZ"] = "UTC"
            time.tzset()
            self.assertEqual(alarm.resolve_at("10:01", datetime(2024, 12, 31, 10, 0).astimezone()).date().isoformat(), "2024-12-31")
            self.assertEqual(alarm.resolve_at("10:00", datetime(2024, 12, 31, 10, 0).astimezone()).date().isoformat(), "2025-01-01")
        finally:
            if previous is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = previous
            if hasattr(time, "tzset"):
                time.tzset()

    def test_rejects_dst_gap_and_overlap(self):
        if not hasattr(time, "tzset"):
            self.skipTest("tzset unavailable")
        previous = os.environ.get("TZ")
        try:
            os.environ["TZ"] = "America/New_York"
            time.tzset()
            for now, target in ((datetime(2025, 3, 9, 1, 0), "02:30"),
                                (datetime(2025, 11, 2, 0, 0), "01:30")):
                with self.subTest(target=target), self.assertRaises(ValueError):
                    alarm.resolve_at(target, now.astimezone())
        finally:
            if previous is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = previous
            time.tzset()

    def test_preview_precedes_countdown_and_ring(self):
        events = []
        ticks = iter([0, 62, 62, 62, 62, 122])

        class FakeAudio:
            def __enter__(self):
                events.append("open")
                return self
            def __exit__(self, *_):
                events.append("close")
            def preview(self, sleep):
                events.append("preview")
            def ring(self):
                events.append("ring")
            def check(self):
                pass
            def stop(self):
                events.append("stop")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = alarm.run(["--in", "1"], audio_factory=FakeAudio,
                               monotonic=lambda: next(ticks), sleep=lambda _: None)
        self.assertEqual(result, 0, output.getvalue())
        self.assertEqual(events, ["open", "preview", "ring", "stop", "close"])

    def test_sound_failure_prevents_arming(self):
        class FailingAudio:
            def __enter__(self):
                return self
            def __exit__(self, *_):
                pass
            def preview(self, sleep):
                raise RuntimeError("device missing")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = alarm.run(["--in", "1"], audio_factory=FailingAudio)
        self.assertEqual(result, 1)
        self.assertIn("Alarm not armed", output.getvalue())
        self.assertNotIn("Press Ctrl+C", output.getvalue())

    def test_clock_alarm_due_during_preview_rings_immediately(self):
        events = []
        current = iter([datetime(2025, 1, 1, 9, 59).astimezone(),
                        datetime(2025, 1, 1, 10, 1).astimezone()])
        ticks = iter([0, 60])

        class FakeAudio:
            def __enter__(self): return self
            def __exit__(self, *_): events.append("close")
            def preview(self, sleep): events.append("preview")
            def ring(self): events.append("ring")
            def stop(self): events.append("stop")
            def check(self): pass

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = alarm.run(["--at", "10:00"], audio_factory=FakeAudio,
                               now=lambda: next(current), monotonic=lambda: next(ticks),
                               sleep=lambda _: None)
        self.assertEqual(result, 0, output.getvalue())
        self.assertEqual(events, ["preview", "ring", "stop", "close"])
        self.assertIn("[ARMED] Ringing at 2025-01-01T10:00", output.getvalue())
        self.assertIn("[RINGING] Alarm!", output.getvalue())

    def test_interrupt_while_waiting_cleans_up(self):
        events = []
        class FakeAudio:
            def __enter__(self): return self
            def __exit__(self, *_): events.append("close")
            def preview(self, sleep): pass
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = alarm.run(["--in", "1"], audio_factory=FakeAudio,
                               monotonic=lambda: 0,
                               sleep=lambda _: (_ for _ in ()).throw(KeyboardInterrupt()))
        self.assertEqual(result, 130)
        self.assertEqual(events, ["close"])
        self.assertIn("[CANCELLED]", output.getvalue())

    def test_countdown_starts_after_preview(self):
        clock = [10]
        events = []
        class FakeAudio:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def preview(self, sleep): clock[0] = 20
            def ring(self): events.append("ring")
            def check(self): pass
            def stop(self): pass
        def sleep(seconds):
            clock[0] += seconds
        with contextlib.redirect_stdout(io.StringIO()):
            result = alarm.run(["--in", "1"], audio_factory=FakeAudio,
                               monotonic=lambda: clock[0], sleep=sleep)
        self.assertEqual(result, 0)
        self.assertEqual(events, ["ring"])
        self.assertGreaterEqual(clock[0], 140)

    def test_ring_playback_failure_is_reported(self):
        class FakeAudio:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def preview(self, sleep): pass
            def ring(self): raise RuntimeError("output lost")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = alarm.run(["--in", "1"], audio_factory=FakeAudio,
                               monotonic=iter([0, 60]).__next__, sleep=lambda _: None)
        self.assertEqual(result, 1)
        self.assertIn("output lost", output.getvalue())

    def test_preview_interrupt_is_cancelled(self):
        class FakeAudio:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def preview(self, sleep): raise KeyboardInterrupt()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = alarm.run(["--test-sound"], audio_factory=FakeAudio)
        self.assertEqual(result, 130)
        self.assertIn("[CANCELLED]", output.getvalue())

    def test_am_pm_conversion_and_separate_cli_suffix(self):
        self.assertEqual(alarm.parse_args(["--at", "05:48", "PM"]).at, "17:48")
        self.assertEqual(alarm.parse_args(["--at", "12:00", "AM"]).at, "00:00")
        self.assertEqual(alarm.parse_args(["--at", "12:00 pm"]).at, "12:00")
        self.assertEqual(alarm.parse_args(["--at", "07:30"]).at, "07:30")

    def test_invalid_am_pm_times_and_alarm_counts_stop_before_audio(self):
        for args in (["--at", "13:00", "PM"], ["--at", "00:30 AM"],
                     ["--at", "5:60 PM"], ["--alarms", "0"],
                     ["--alarms", "two"], ["--alarms", "2", "--in", "1"]):
            with self.subTest(args=args), patch.object(alarm, "Audio") as audio:
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as exit_:
                        alarm.main(args)
                self.assertEqual(exit_.exception.code, 2)
                audio.assert_not_called()

    def test_multiple_alarm_prompts_and_chronological_ringing(self):
        clock = [0.0]
        base = datetime(2025, 1, 1, 9, 59).astimezone()
        entries = iter(["10:02 AM", "10:00 AM"])
        prompts = []
        rings = []

        class FakeAudio:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def preview(self, sleep): pass
            def ring(self): rings.append(clock[0])
            def check(self): pass
            def stop(self): pass

        def ask(prompt):
            prompts.append(prompt)
            return next(entries)

        def sleep(seconds):
            clock[0] += seconds

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = alarm.run(["--alarms", "2"], audio_factory=FakeAudio,
                               input_func=ask, now=lambda: base + timedelta(seconds=clock[0]),
                               monotonic=lambda: clock[0], sleep=sleep)
        self.assertEqual(result, 0, output.getvalue())
        self.assertEqual(len(prompts), 2)
        self.assertEqual(rings, [60.0, 180.0])
        self.assertEqual(output.getvalue().count("[RINGING]"), 2)

    def test_bad_prompted_time_prevents_any_alarm_from_arming(self):
        entries = iter(["10:00 AM", "banana"])
        output = io.StringIO()
        with patch.object(alarm, "Audio") as audio, contextlib.redirect_stderr(output):
            result = alarm.run(["--alarms", "2"], input_func=lambda _: next(entries))
        self.assertEqual(result, 2)
        audio.assert_not_called()
        self.assertIn("Invalid time", output.getvalue())

    def test_noninteractive_times_are_validated_and_do_not_prompt(self):
        args = alarm.parse_args(["--alarms", "2", "--times", "10:02 AM", "10:00 AM"])
        self.assertEqual(args.times, ["10:02", "10:00"])

        class FailingAudio:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def preview(self, sleep): raise RuntimeError("stop after input")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = alarm.run(["--alarms", "2", "--times", "10:02 AM", "10:00 AM"],
                               audio_factory=FailingAudio,
                               input_func=lambda _: self.fail("prompted despite --times"))
        self.assertEqual(result, 1)
        self.assertIn("stop after input", output.getvalue())

    def test_noninteractive_time_count_and_invalid_time_are_rejected(self):
        for args in (["--alarms", "2", "--times", "10:00 AM"],
                     ["--alarms", "2", "--times", "10:00 AM", "banana"],
                     ["--times", "10:00 AM", "11:00 AM"]):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as exit_:
                    alarm.parse_args(args)
            self.assertEqual(exit_.exception.code, 2)

    def test_eof_explains_noninteractive_option(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            result = alarm.run(["--alarms", "2"],
                               input_func=lambda _: (_ for _ in ()).throw(EOFError()))
        self.assertEqual(result, 2)
        self.assertIn("--times", output.getvalue())


if __name__ == "__main__":
    unittest.main()
