#!/usr/bin/env python

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from typing import Optional

PIDFILE = "/tmp/swayidle_presets.pid.json"
SWAYEXIT_SCRIPT = "~/.config/sway/swayexit"

# Dict of modes where each entry is a tuple of blank screen timeout, lock screen
# timeout, and suspend timeout
MODES = {"short": (120, 300, 600), "medium": (300, 600, 900), "long": (600, 900, 1200)}


@dataclass
class ProcInfo:
    pid: int
    mode: str


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run swayidle with different preset modes. Without "
        "options, simply print current mode if running."
    )
    parser.add_argument("mode", help='The mode to run with, or "next"', nargs="?")
    parser.add_argument(
        "--list_modes", help="List the available modes", action="store_true"
    )
    parser.add_argument(
        "--current_mode",
        help="List the current running mode info as json (for waybar)",
        action="store_true",
    )
    parser.add_argument(
        "--signal_waybar",
        help="Sends SIGRTMIN+N to waybar when it should update. Only for ops that set mode.",
        type=int,
    )
    args = parser.parse_args()

    if args.list_modes:
        print_modes()
    elif args.current_mode:
        print_current_mode()
    elif args.mode:
        try:
            run_mode(args.mode, args.signal_waybar)
        except TerminationForModeChangeException:
            print("Exiting gracefully for mode change")
    else:
        parser.print_usage()
        sys.exit(1)


def print_modes() -> None:
    print(json.dumps(list(MODES.keys())))


def get_existing_proc_info() -> Optional[ProcInfo]:
    """Checks for existing process by pidfile and returns info"""
    try:
        with open(PIDFILE, "r") as pidfile:
            info = ProcInfo(**json.load(pidfile))
    except FileNotFoundError:
        return None

    if pid_exists(info.pid):
        return info
    else:
        return None


def get_waybar_pid() -> Optional[int]:
    res = subprocess.run(["pgrep", "-d", " ", "waybar"], capture_output=True)
    if res.returncode != 0:
        return None
    else:
        return int(res.stdout.decode().split(" ")[0])


def kill_and_wait(pid: int, signal: signal.Signals) -> None:
    os.kill(pid, signal)
    while pid_exists(pid):
        time.sleep(0.05)


def pid_exists(pid: int) -> bool:
    """Check For the existence of a unix pid."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True


class TerminationForModeChangeException(Exception):
    """Raised when the process is killed to change modes"""


def sigusr1_handler(*args) -> None:
    # Just raise an exception so that files are closed
    raise TerminationForModeChangeException()


def print_current_mode() -> None:
    """Prints current mode info as json for waybar"""
    info = get_existing_proc_info()
    if info:
        print(
            json.dumps(
                {
                    "text": info.mode,
                    "tooltip": "Monitor after {} seconds, lock after {} seconds, "
                    "suspend after {} seconds".format(*MODES[info.mode]),
                },
            )
        )
    else:
        print(json.dumps({"text": "No idle mode"}))


def run_mode(mode: str, signal_waybar: Optional[int]) -> None:
    info = get_existing_proc_info()
    if mode == "next":
        if info is None:
            mode = list(MODES.items())[0][0]
        else:
            cur_mode_idx = list(MODES.keys()).index(info.mode)
            mode = list(MODES.items())[(cur_mode_idx + 1) % len(MODES)][0]
    elif mode not in MODES:
        print('"{}" is not a valid mode'.format(mode), file=sys.stderr)
        sys.exit(1)

    # Kill the previous running process/mode if its going
    if info is not None:
        kill_and_wait(info.pid, signal.SIGUSR1)

    # Write to the pidfile
    with open(PIDFILE, "w+") as f:
        json.dump(asdict(ProcInfo(os.getpid(), mode)), f)

    if signal_waybar is not None and (waybar_pid := get_waybar_pid()) is not None:
        os.kill(waybar_pid, signal.SIGRTMIN + signal_waybar)

    blank_screen_timeout, lock_screen_timeout, suspend_timeout = MODES[mode]
    # handle SIGUSR1 as termination from a new instance coming up
    signal.signal(signal.SIGUSR1, sigusr1_handler)
    try:
        subprocess.run(
            [
                "swayidle",
                "-w",
                "timeout",
                str(blank_screen_timeout),
                'swaymsg "output * dpms off"',
                "resume",
                'swaymsg "output * dpms on"',
                "timeout",
                str(lock_screen_timeout),
                f"{SWAYEXIT_SCRIPT} lock",
                "timeout",
                str(suspend_timeout),
                "systemctl suspend",
                "after-resume",
                'swaymsg "output * dpms on"',
                "before-sleep",
                f"{SWAYEXIT_SCRIPT} lock",
            ]
        )
    finally:
        # delete the tmp file
        os.remove(PIDFILE)


if __name__ == "__main__":
    main()
