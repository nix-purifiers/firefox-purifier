"""Consume exported native image output, external locks and exact release assets."""

import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

cli = Path(sys.argv[1]).resolve() / "bin/firefox-purifier"
source = Path(__file__).resolve().parents[1]


def call(arguments, *, env, cwd):
    result = subprocess.run(
        arguments, check=False, env=env, cwd=cwd, text=True, capture_output=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


with tempfile.TemporaryDirectory(prefix="firefox-artifacts-") as temporary:
    root = Path(temporary)
    project = root / "project"
    shutil.copytree(
        source / "examples/minimal",
        project,
        ignore=shutil.ignore_patterns(".firefox-purifier"),
    )
    env = os.environ.copy()
    args = [str(cli), "--project", str(project)]
    build = Path(call([*args, "build"], env=env, cwd=root))
    image = build / "page.png"
    assert image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    release = Path(call([*args, "bundle"], env=env, cwd=root))
    archive = release / "firefox-project.tar.gz"
    with tarfile.open(archive) as tar:
        assert tar.extractfile("./page.png").read() == (build / "page.png").read_bytes()
    external = root / "external-lock.json"
    shutil.copyfile(project / "firefox-purifier.lock.json", external)
    replay = Path(call([*args, "--lock", str(external), "bundle"], env=env, cwd=root))
    assert (replay / archive.name).read_bytes() == archive.read_bytes()
    fake = root / "gh"
    fake.write_text(
        f"#!{sys.executable}\nimport json,os,sys\nfrom pathlib import Path\n"
        "Path(os.environ['UPLOAD_RECORD']).write_text(json.dumps(sys.argv[1:]))\n"
        "Path(os.environ['UPLOAD_BYTES']).write_bytes(Path(sys.argv[4]).read_bytes())\n"
    )
    fake.chmod(0o755)
    publish_env = env | {
        "FIREFOX_PURIFIER_GH": str(fake),
        "UPLOAD_RECORD": str(root / "upload.json"),
        "UPLOAD_BYTES": str(root / "upload.tar.gz"),
    }
    call([*args, "publish", "--tag", "proof"], env=publish_env, cwd=root)
    record = json.loads((root / "upload.json").read_text())
    assert record[:3] == ["release", "upload", "proof"] and record[3] == str(archive)
    assert (root / "upload.tar.gz").read_bytes() == archive.read_bytes()
print("Firefox archive, external lock and exact release asset checks passed")
