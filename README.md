# AlarmClock

Foreground alarms for a terminal on Windows, macOS, or Linux. The app requires Python 3.11 or newer and a working desktop audio output. Keep the terminal open and the computer awake until all alarms ring.

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
python alarm.py --at 05:48 PM
python alarm.py --alarms 3
python alarm.py --alarms 3 --times "05:48 PM" "06:15 PM" "07:00 PM"
python alarm.py --in 10
python alarm.py --test-sound
python alarm.py --help
```

`--at` accepts local 24-hour `HH:MM` or 12-hour `H:MM AM/PM` time. For 12-hour input, `05:48 PM` works as two arguments or as one quoted argument. `--alarms COUNT` asks for that many times, one by one, in an interactive terminal. If your command runner cannot accept typed responses, add `--times` with exactly COUNT quoted times. The alarms ring in time order, even if you enter them out of order.

Each clock time is scheduled for today if it is still in the future, otherwise tomorrow. The displayed targets include their dates and UTC offsets. Ambiguous and nonexistent times during daylight-saving changes are rejected. `--in` accepts 1 to 1,440 whole minutes; its countdown begins after the sound preview.

After all times are valid, the app plays one two-second sound preview before arming the alarms. If playback fails, none are armed. Each alarm sounds for up to 60 seconds. Press Ctrl+C to cancel all pending alarms at any stage.

Exit codes: `0` for completion, help, or a successful standalone sound test; `1` for audio failures; `2` for invalid input or an invalid local time; `130` for cancellation.

Alarms do not survive closing the terminal or computer sleep, and cannot wake a sleeping computer. Muted output or an output-device change can prevent notification. The app does not save alarms, repeat them on later days, or snooze them.

## Verification

Run automated tests with:

```sh
python -m unittest discover -s tests -v
```

The automated suite uses fake clocks and audio; it does not prove that sound is audible. Installation and a completed sound preview were verified on macOS 26.6.2 with Python 3.14.6 and pygame-ce 2.5.8. Actual audibility needs a listener's confirmation. Windows and Linux have not been tested on this machine.
