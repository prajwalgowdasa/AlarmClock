# Python CLI Alarm Clock Plan

**Status:** Proposed; awaiting user review. Do not begin implementation until approved.

## Goal and scope

Build a small personal alarm clock that runs in the terminal on Windows, macOS, and Linux. Interpret “all OS platforms” as these desktop platforms, not mobile or every OS/distribution ever released.

- One foreground alarm per invocation; keep the terminal open and computer awake.
- Python 3.11 or newer, subject to verifying the supported Python/audio dependency combinations.
- Set a local clock-time alarm with `python alarm.py --at 07:30`.
- Set a duration alarm with `python alarm.py --in 10` (minutes).
- Provide `--help` and a standalone `--test-sound` option.
- Automatically test sound every time an alarm is set.
- No web UI, React, database, or persistence.

This scope provides useful clock-time alarms and short reminders without the complexity of a service or alarm manager.

## Expected behavior

### Inputs and fresh system time

- Require exactly one mode: `--at`, `--in`, or `--test-sound`.
- Accept strict 24-hour `HH:MM` for `--at`, from `00:00` to `23:59`; seconds are zero.
- Accept whole-number durations from 1 to 1,440 minutes for `--in`.
- Reject missing/conflicting options, malformed times, and invalid durations before playing sound. Explain the error, show a valid example, and exit `2` without a traceback.
- Every invocation reads the current system time and local timezone afresh. Never reuse a prior invocation’s reference time or alarm.
- For `--at`, choose today if the requested instant is strictly in the future; otherwise choose tomorrow. Print the full resolved date, time, and UTC offset so rollover is clear.
- Separate invocations are independent; starting another process does not cancel an existing alarm.

### Initial sound test

1. Validate inputs and resolve any clock-time target.
2. Print and flush `[SOUND TESTING] Playing a 2-second preview…` before starting playback.
3. Play the bundled sound using the same audio backend and output as the alarm.
4. On success, stop the preview and print `[SOUND TEST COMPLETE] Preview finished. If silent, check volume/output.`
5. Arm the alarm and print its target and `Press Ctrl+C to cancel.`

If audio initialization, loading, or playback fails, print `[ERROR] Sound test failed: <reason>. Alarm not armed.` and exit `1`. Do not silently substitute a terminal bell. A successful playback call cannot establish that the user heard the sound, so do not claim audibility or require an additional confirmation prompt.

Standalone `--test-sound` performs the preview and exits without scheduling an alarm.

### Time handling

- `--in`: start the countdown after the preview finishes. Use a monotonic clock so system clock adjustments do not change the duration.
- `--at`: preserve the target instant resolved before the preview. If it becomes due during testing, ring immediately after the preview; do not move it to tomorrow.
- Resolve clock-time targets in the system’s local timezone. Later timezone changes do not reinterpret an already scheduled target.
- Reject ambiguous or nonexistent daylight-saving times with an explanation; do not guess which instant the user intended.
- Clock-time alarms follow the system clock: a forward jump past the target triggers once; a backward adjustment postpones reaching the target.
- Check deadlines using brief sleeps, without busy-waiting. Aim to trigger within one second while the machine is awake; this is not a real-time guarantee.

### Ringing, cancellation, and exits

- Print `[RINGING] Alarm!` and repeat the sound for up to 60 seconds, then stop and exit `0`.
- `Ctrl+C` during testing, waiting, or ringing stops playback, releases audio resources, prints `[CANCELLED]`, and exits `130` without a traceback.
- Playback failures during ringing produce a clear error and exit `1`; never report successful ringing after a detected failure.
- Successful help and standalone sound testing exit `0`.

## Design and dependency tradeoffs

Use simple functions for parsing, target calculation, waiting, and audio control. Avoid a class hierarchy, scheduler framework, threads, and platform-specific shell players unless implementation evidence establishes a need.

Planned files:

| File | Responsibility |
| --- | --- |
| `alarm.py` | CLI, time calculation, waiting loop, and small audio wrapper |
| `assets/alarm.wav` | Short bundled sound used for preview and ringing |
| `tests/test_alarm.py` | Validation, time, state transitions, failures, and cleanup tests |
| `requirements.txt` | Verified, pinned audio dependency |
| `README.md` | Installation, examples, behavior, supported environments, and limitations |

Use standard-library `argparse`, `datetime`, `time`, and `unittest`. Use `pygame.mixer` as the single third-party runtime dependency and initialize audio only, without opening a window. Locate the WAV relative to the script rather than the caller’s working directory.

Pygame adds installation weight but avoids maintaining separate Windows, macOS, and Linux playback implementations. A terminal bell is smaller but may be disabled or inaudible. Verify a compatible Pygame version before pinning it; document any required Linux audio packages discovered during validation.

Pass clock/sleep functions and audio operations into the relevant logic so automated tests need neither real waiting nor speakers.

References: [Pygame installation](https://www.pygame.org/wiki/GettingStarted), [mixer documentation](https://www.pygame.org/docs/ref/mixer.html).

## Implementation and testing sequence

After plan approval, implement and verify each step before proceeding:

1. **CLI and validation:** implement the three exclusive modes and help. Test valid inputs, missing/conflicting options, malformed times, and duration boundaries. Verify invalid input never starts audio.
2. **Time calculation:** implement fresh per-run time capture and target resolution. Test today/tomorrow, exact-minute equality, midnight, month/year rollover, leap days, and daylight-saving gaps/overlaps. Verify the platform timezone conversion behavior on all supported OSes.
3. **Audio wrapper:** implement initialization, loading, preview, looping playback, stopping, and cleanup. Test missing assets, unavailable devices, initialization/playback failures, and use from another working directory.
4. **Lifecycle:** connect validation → sound testing → armed → ringing → finished. Use fake clocks/audio to test preview ordering, countdown start after testing, deadlines crossed during testing, no early/double triggers, and forward/backward wall-clock changes.
5. **Cancellation and errors:** test interruption during preview, waiting, and ringing; verify exit codes, no traceback for expected errors, and audio cleanup on every exit path.
6. **Platform verification and documentation:** run `python -m unittest discover -s tests -v` on Windows, macOS, and Linux. Manually verify preview audibility, actual ringing, cancellation, and installation on each platform. Document exact verified OS/Python combinations and any untested environments.

Automated audio mocks verify control flow, not actual sound. Cross-platform support is not considered verified solely because mocked tests pass.

## Limitations and non-goals

- No recurring alarms, snooze, custom sounds, managed alarm lists, configuration files, or saved alarms.
- No background daemon, OS scheduler integration, wake-from-sleep feature, or guarantee after terminal/process termination.
- Closing the process loses its alarm. Muted audio, output-device changes, or suspension can prevent notification.
- If a clock-time target is overdue when the process resumes, ring once. Duration behavior across suspension depends on platform clock behavior; suspend-aware countdowns are outside version one’s guarantee.
- Support assumes a working desktop audio environment. Headless servers, containers, WSL, and mobile environments are not initial acceptance targets.
- No packaging into native installers or executables initially; run the Python CLI directly.

## Definition of done

- Both alarm modes match the agreed input and time semantics, including fresh system time on every invocation.
- Every valid alarm setup visibly enters sound testing before arming; detected audio failures prevent arming.
- Cancellation stops sound and releases resources in every state.
- Automated tests pass on all three supported OSes, and real playback is manually verified on each.
- README documents setup, examples, exit codes, verified environments, and limitations.
- No GUI, database, persistence, or unrelated features have been introduced.

**Next action:** User reviews this plan. Coding remains pending approval.
