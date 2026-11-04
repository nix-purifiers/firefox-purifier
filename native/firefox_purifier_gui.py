"""Keep native profile locking and stop failed locked startup before continuing."""

import json
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path


def launch(state, environment, arguments):
    state, environment = Path(state).resolve(), Path(environment).resolve()
    options = {argument.split("=", 1)[0].lower() for argument in arguments}
    if options & {"--app", "-app"}:
        raise ValueError("This provider supports the pinned Firefox application")
    profile_options = {
        "--profile",
        "-profile",
        "-p",
        "--profilemanager",
        "-profilemanager",
    }
    profile_arguments = []
    if not options & profile_options:
        profile = state / "profile"
        profile.mkdir(parents=True, exist_ok=True)
        profile_arguments = ["--profile", str(profile)]
    with tempfile.TemporaryDirectory(prefix="launch-", dir=state) as temporary:
        startup = Path(temporary) / "startup.json"
        env = os.environ.copy()
        for key in ["MOZ_APP_DATA", "MOZILLA_FIVE_HOME", "MOZ_MARIONETTE"]:
            env.pop(key, None)
        env.update(
            FIREFOX_PURIFIER_ENVIRONMENT=str(environment),
            FIREFOX_PURIFIER_STARTUP=str(startup),
        )
        process = subprocess.Popen(
            [
                environment / "sdk/bin/firefox",
                "--no-remote",
                *profile_arguments,
                *arguments,
            ],
            env=env,
            start_new_session=True,
        )
        try:
            initialized = False
            deadline = time.monotonic() + 60
            while process.poll() is None:
                if startup.exists():
                    try:
                        status = json.loads(startup.read_text())
                    except json.JSONDecodeError:
                        time.sleep(0.02)
                        continue
                    if status.get("error"):
                        raise ValueError(status["error"])
                    if status.get("ready") is True:
                        initialized = True
                        break
                    raise ValueError("Invalid native Firefox startup handshake")
                if time.monotonic() >= deadline:
                    raise ValueError(
                        "Firefox did not initialize its locked extension location"
                    )
                time.sleep(0.02)
            code = process.wait()
            if not initialized and startup.exists():
                status = json.loads(startup.read_text())
                if status.get("error"):
                    raise ValueError(status["error"])
                initialized = status.get("ready") is True
            immediate = options & {
                "--version",
                "-version",
                "-v",
                "--full-version",
                "--help",
                "-help",
                "-h",
                "--createprofile",
                "-createprofile",
                "--profilemanager",
                "-profilemanager",
            }
            return code if initialized or code or immediate else 1
        finally:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
