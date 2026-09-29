import contextlib
import io
import os
import time
import unittest
from datetime import datetime
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


if __name__ == "__main__":
    unittest.main()
