"""Run ordinary Python project code with a native, locked Firefox driver."""

import runpy
import sys
import tempfile
from pathlib import Path

from firefox_purifier_driver import browser


def run_project(project, script, state, environment, output):
    project, state = Path(project).resolve(), Path(state).resolve()
    environment, output = Path(environment).resolve(), Path(output).resolve()
    state.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    with (
        tempfile.TemporaryDirectory(prefix="launch-", dir=state) as temporary,
        browser(
            temporary,
            environment / "sdk",
            environment=environment,
            profile=state / "profile",
        ) as driver,
    ):
        driver.set_window_size(900, 700)
        previous_argv = sys.argv
        sys.argv = [str(script)]
        try:
            runpy.run_path(
                str(script),
                run_name="__main__",
                init_globals={
                    "driver": driver,
                    "project": project,
                    "output": output,
                },
            )
        finally:
            sys.argv = previous_argv
    return 0


if __name__ == "__main__":
    raise SystemExit(run_project(*sys.argv[1:]))
