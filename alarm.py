"""Foreground terminal alarms."""

import argparse
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


SOUND_FILE = Path(__file__).resolve().parent / "assets" / "alarm.wav"


class AlarmParser(argparse.ArgumentParser):
    def error(self, message):
        super().error(f"{message}. Example: python alarm.py --at 05:48 PM")


def parse_clock_time(value):
    """Return a local clock time as 24-hour HH:MM."""
    value = value.strip()
    match = re.fullmatch(r"(1[0-2]|0?[1-9]):([0-5][0-9])\s*([AaPp][Mm])", value)
    if match:
        hour = int(match.group(1)) % 12
        if match.group(3).upper() == "PM":
            hour += 12
        return f"{hour:02d}:{match.group(2)}"
    if re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value):
        return value
    raise ValueError("Invalid time; use HH:MM (24-hour) or HH:MM AM/PM")


def parse_args(argv):
    parser = AlarmParser(description="Set foreground alarms (keep this terminal open).")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--at", nargs="+", metavar="TIME", help="one local time, e.g. 17:48 or 05:48 PM")
    modes.add_argument("--alarms", metavar="COUNT", help="prompt for COUNT local alarm times")
    modes.add_argument("--in", dest="minutes", metavar="MINUTES", help="1–1440 minutes from the end of the sound test")
    modes.add_argument("--test-sound", action="store_true", help="play a two-second preview and exit")
    parser.add_argument("--times", nargs="+", metavar="TIME",
                        help="supply all --alarms times without interactive prompts; quote AM/PM times")
    args = parser.parse_args(argv)
    if args.at is not None:
        try:
            args.at = parse_clock_time(" ".join(args.at))
        except ValueError as exc:
            parser.error(str(exc))
    if args.alarms is not None:
        if not re.fullmatch(r"[0-9]+", args.alarms) or int(args.alarms) < 1:
            parser.error("--alarms must be a positive whole number")
        args.alarms = int(args.alarms)
    if args.times is not None:
        if args.alarms is None:
            parser.error("--times requires --alarms COUNT")
        if len(args.times) != args.alarms:
            parser.error(f"--times requires exactly {args.alarms} time(s)")
        try:
            args.times = [parse_clock_time(value) for value in args.times]
        except ValueError as exc:
            parser.error(str(exc))
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


def run(argv, *, audio_factory=Audio, now=None, monotonic=time.monotonic,
        sleep=time.sleep, input_func=input):
    args = parse_args(argv)
    now = now or (lambda: datetime.now().astimezone())
    clock_times = args.times if args.times is not None else ([args.at] if args.at else [])
    if args.alarms is not None and args.times is None:
        try:
            for index in range(1, args.alarms + 1):
                entry = input_func(f"Alarm {index}/{args.alarms} time (HH:MM AM/PM or 24-hour HH:MM): ")
                clock_times.append(parse_clock_time(entry))
        except KeyboardInterrupt:
            print("[CANCELLED]", flush=True)
            return 130
        except EOFError:
            print("[ERROR] No interactive input is available. Supply all times with --times, for example: --alarms 2 --times '05:48 PM' '06:30 PM'. Alarm not armed.", file=sys.stderr)
            return 2
        except ValueError as exc:
            print(f"[ERROR] {exc}. Alarm not armed.", file=sys.stderr)
            return 2
    try:
        reference = now() if clock_times else None
        targets = sorted((resolve_at(value, reference) for value in clock_times),
                         key=lambda target: target.timestamp())
    except ValueError as exc:
        print(f"[ERROR] {exc}. Example: python alarm.py --at 05:48 PM", file=sys.stderr)
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
                targets = [None]
            else:
                if len(targets) == 1:
                    print(f"[ARMED] Ringing at {targets[0].isoformat(timespec='minutes')}. Press Ctrl+C to cancel.", flush=True)
                else:
                    for index, target in enumerate(targets, 1):
                        print(f"[ARMED] Alarm {index}: {target.isoformat(timespec='minutes')}", flush=True)
                    print("Press Ctrl+C to cancel.", flush=True)
            for index, target in enumerate(targets, 1):
                if target is not None:
                    while now().timestamp() < target.timestamp():
                        sleep(min(0.25, max(0, target.timestamp() - now().timestamp())))
                stage = "ringing"
                print("[RINGING] Alarm!" if len(targets) == 1 else
                      f"[RINGING] Alarm {index}/{len(targets)}!", flush=True)
                audio.ring()
                end = monotonic() + 60
                while monotonic() < end:
                    audio.check()
                    sleep(min(0.25, max(0, end - monotonic())))
                audio.stop()
                stage = "waiting"
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
