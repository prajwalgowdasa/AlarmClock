# AlarmClock

A single foreground alarm for a terminal on Windows, macOS, or Linux. It requires Python 3.11 or newer and a working desktop audio output. Keep the terminal open and the computer awake until the alarm rings.

## Install

Create a virtual environment, activate it, and install the pinned audio package:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, activate with `.venv\Scripts\activate` instead. Use the virtual environment's `python` for the commands below. The dependency is `pygame-ce`, which provides the `pygame.mixer` module. On Linux, a working SDL audio backend and system audio service are required.

## Use

```sh
python alarm.py --at 07:30
python alarm.py --in 10
python alarm.py --test-sound
python alarm.py --help
```

`--at` accepts a local 24-hour `HH:MM` time. If that time has passed or is exactly now, the alarm is set for tomorrow. The displayed target includes its date and UTC offset. Ambiguous and nonexistent times during daylight-saving changes are rejected. `--in` accepts 1 to 1,440 whole minutes; its countdown begins after the sound preview.

Every valid alarm begins with a two-second sound preview. If playback fails, the alarm is not armed. After the alarm rings, the sound repeats for up to 60 seconds. Press Ctrl+C to cancel at any stage.

Exit codes: `0` for completion, help, or a successful standalone sound test; `1` for audio failures; `2` for invalid input or an invalid local time; `130` for cancellation.

The alarm does not survive closing the terminal or computer sleep, and cannot wake a sleeping computer. Muted output or an output-device change can prevent notification. The app does not save, repeat, or snooze alarms.

## Verification

Run automated tests with:

```sh
python -m unittest discover -s tests -v
```

The automated suite uses fake clocks and audio; it does not prove that sound is audible. Installation and a completed sound preview were verified on macOS 26.6.2 with Python 3.14.6 and pygame-ce 2.5.8. Actual audibility needs a listener's confirmation. Windows and Linux have not been tested on this machine.
