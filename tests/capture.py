"""Fresh native capture, cold replay and atomic failure against the public catalog."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

cli = Path(sys.argv[1]).resolve() / "bin/firefox-purifier"
source = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="firefox-capture-") as temporary:
    project = Path(temporary)
    shutil.copyfile(
        source / "examples/minimal/firefox-purifier.json",
        project / "firefox-purifier.json",
    )
    env = os.environ.copy() | {"FIREFOX_PURIFIER_PROJECT": str(project)}
    subprocess.run([str(cli), "lock", "--update"], check=True, env=env, cwd=project)
    lock = project / "firefox-purifier.lock.json"
    before = lock.read_bytes()
    subprocess.run([str(cli), "lock"], check=True, env=env, cwd=project)
    subprocess.run([str(cli), "prefetch"], check=True, env=env, cwd=project)
    assert lock.read_bytes() == before
    selection_file = project / "firefox-purifier.json"
    selection = json.loads(selection_file.read_text())
    selection["extensions"].append("org.nix-purifiers.missing-probe-999999999999")
    selection_file.write_text(json.dumps(selection))
    failed = subprocess.run(
        [str(cli), "lock", "--update"], check=False, env=env, cwd=project
    )
    assert failed.returncode != 0 and lock.read_bytes() == before
    empty = project / "empty"
    empty.mkdir()
    (empty / "firefox-purifier.json").write_text('{"extensions": []}\n')
    empty_env = env | {"FIREFOX_PURIFIER_PROJECT": str(empty)}
    subprocess.run([str(cli), "lock", "--update"], check=True, env=empty_env, cwd=empty)
    (empty / "exit.py").write_text("pass\n")
    subprocess.run([str(cli), "run", "exit.py"], check=True, env=empty_env, cwd=empty)


print("native firefox capture and atomic failure passed")
