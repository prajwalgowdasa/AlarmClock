"""A single foreground terminal alarm."""

import argparse
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


SOUND_FILE = Path(__file__).resolve().parent / "assets" / "alarm.wav"


class AlarmParser(argparse.ArgumentParser):
    def error(self, message):
        super().error(f"{message}. Example: python alarm.py --at 07:30")


def parse_args(argv):
    parser = AlarmParser(description="Set one foreground alarm (keep this terminal open).")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--at", metavar="HH:MM", help="local 24-hour clock time")
    modes.add_argument("--in", dest="minutes", metavar="MINUTES", help="1–1440 minutes from the end of the sound test")
    modes.add_argument("--test-sound", action="store_true", help="play a two-second preview and exit")
    args = parser.parse_args(argv)
    if args.at is not None and (not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", args.at)):
        parser.error("--at must be a valid 24-hour HH:MM time")
    if args.minutes is not None:
        if not re.fullmatch(r"[0-9]+", args.minutes) or not 1 <= int(args.minutes) <= 1440:
            parser.error("--in must be a whole number from 1 to 1440")
        args.minutes = int(args.minutes)
    return args


def _local_instant(day: date, hour: int, minute: int) -> datetime:
    """Resolve a local wall time by round-tripping both DST interpretations."""
    matches = {}
    for dst in (0, 1):
        stamp = time.mktime((day.year, day.month, day.day, hour, minute, 0, 0, 0, dst))
        local = time.localtime(stamp)
        if (local.tm_year, local.tm_mon, local.tm_mday, local.tm_hour, local.tm_min) == (
            day.year, day.month, day.day, hour, minute
        ):
            matches[stamp] = datetime.fromtimestamp(stamp, timezone.utc).astimezone()
    if not matches:
        raise ValueError("that local time does not exist because of a daylight-saving change")
    if len(matches) > 1:
        raise ValueError("that local time is ambiguous because of a daylight-saving change")
    return next(iter(matches.values()))


def resolve_at(value: str, now: datetime) -> datetime:
    hour, minute = map(int, value.split(":"))
    today = now.astimezone().date()
    target = _local_instant(today, hour, minute)
    if target.timestamp() <= now.timestamp():
        target = _local_instant(today + timedelta(days=1), hour, minute)
    return target


class Audio:
    def __enter__(self):
        try:
            import pygame.mixer
            self.mixer = pygame.mixer
            self.mixer.init()
            self.sound = self.mixer.Sound(str(SOUND_FILE))
            self.channel = None
            return self
        except BaseException:
            if hasattr(self, "mixer"):
                self.mixer.quit()
            raise

    def __exit__(self, *_):
        try:
            self.stop()
        finally:
            self.mixer.quit()

    def preview(self, sleep):
        self.channel = self.sound.play(loops=-1)
        if self.channel is None:
            raise RuntimeError("no audio channel is available")
        try:
            end = time.monotonic() + 2
            while time.monotonic() < end:
                if not self.channel.get_busy():
                    raise RuntimeError("preview playback stopped unexpectedly")
                sleep(min(0.1, end - time.monotonic()))
        finally:
            self.stop()

    def ring(self):
        self.channel = self.sound.play(loops=-1)
        if self.channel is None:
            raise RuntimeError("no audio channel is available")

    def check(self):
        if not self.channel.get_busy():
            raise RuntimeError("alarm playback stopped unexpectedly")

    def stop(self):
        if getattr(self, "channel", None) is not None:
            self.channel.stop()
            self.channel = None


def run(argv, *, audio_factory=Audio, now=None, monotonic=time.monotonic, sleep=time.sleep):
    args = parse_args(argv)
    now = now or (lambda: datetime.now().astimezone())
    try:
        target = resolve_at(args.at, now()) if args.at else None
    except ValueError as exc:
        print(f"[ERROR] {exc}. Example: python alarm.py --at 07:30", file=sys.stderr)
        return 2

    stage = "testing"
    try:
        print("[SOUND TESTING] Playing a 2-second preview…", flush=True)
        with audio_factory() as audio:
            audio.preview(sleep)
            print("[SOUND TEST COMPLETE] Preview finished. If silent, check volume/output.", flush=True)
            if args.test_sound:
                return 0
            stage = "waiting"
            if args.minutes is not None:
                deadline = monotonic() + args.minutes * 60
                print(f"[ARMED] Ringing in {args.minutes} minute(s). Press Ctrl+C to cancel.", flush=True)
                while monotonic() < deadline:
                    sleep(min(0.25, max(0, deadline - monotonic())))
            else:
                print(f"[ARMED] Ringing at {target.isoformat(timespec='minutes')}. Press Ctrl+C to cancel.", flush=True)
                while now().timestamp() < target.timestamp():
                    sleep(min(0.25, max(0, target.timestamp() - now().timestamp())))
            stage = "ringing"
            print("[RINGING] Alarm!", flush=True)
            audio.ring()
            end = monotonic() + 60
            while monotonic() < end:
                audio.check()
                sleep(min(0.25, max(0, end - monotonic())))
            audio.stop()
            return 0
    except KeyboardInterrupt:
        print("[CANCELLED]", flush=True)
        return 130
    except Exception as exc:
        if stage == "testing":
            print(f"[ERROR] Sound test failed: {exc}. Alarm not armed.", flush=True)
        else:
            print(f"[ERROR] Alarm failed during {stage}: {exc}.", flush=True)
        return 1


def main(argv=None):
    return run(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    sys.exit(main())
