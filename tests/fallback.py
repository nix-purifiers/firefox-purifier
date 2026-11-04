"""The no-lock route adds one warning and preserves the native process contract."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

source = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="firefox-fallback-") as temporary:
    root = Path(temporary)
    binary = root / "native/bin/firefox"
    binary.parent.mkdir(parents=True)
    binary.write_text(
        f"#!{sys.executable}\n"
        "import os,sys\n"
        "assert sys.argv[1:] == ['--profile', 'a profile', '--some-native-flag']\n"
        "os.write(1,b'native stdout\\x00\\n')\n"
        "os.write(2,b'native stderr\\x00\\n')\n"
        "raise SystemExit(23)\n"
    )
    binary.chmod(0o755)
    env = os.environ.copy() | {
        "PYTHONPATH": str(source),
        "FIREFOX_PURIFIER_COMMAND": "firefox",
        "FIREFOX_PURIFIER_ORIGINAL": str(root / "native"),
        "FIREFOX_PURIFIER_PROJECT": str(root),
        "FIREFOX_PURIFIER_LOCK": str(root / "absent.lock.json"),
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "firefox_purifier.main",
            "--profile",
            "a profile",
            "--some-native-flag",
        ],
        env=env,
        cwd=root,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 23
    assert result.stdout == b"native stdout\x00\n"
    assert result.stderr == (
        b"warning: no Firefox purifier lock; using ordinary, impure extension resolution\n"
        b"native stderr\x00\n"
    )
print("No-lock warning preserves native arguments, bytes and exit status")
