"""Exercise the installed integration with the native Firefox application."""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cli", type=Path)
    args = parser.parse_args()
    cli = args.cli.resolve()
    fixture = Path(__file__).resolve().parents[1] / "examples/minimal"
    with tempfile.TemporaryDirectory(prefix="firefox-conformance-") as temporary:
        project = Path(temporary)
        for name in [
            "build.py",
            "answer.json",
            "firefox-purifier.json",
            "firefox-purifier.lock.json",
        ]:
            shutil.copyfile(fixture / name, project / name)

        def run(*arguments, status=0):
            result = subprocess.run(
                [str(cli), *arguments],
                cwd=project,
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == status, result.stdout + result.stderr
            return result

        shutil.copyfile(Path(__file__).with_name("runtime.py"), project / "runtime.py")

        for counter in [1, 2]:
            (project / "counter.json").write_text(json.dumps(counter))
            run("run", "runtime.py")

        hashes = []
        for answer in [42, 43, 42]:
            (project / "answer.json").write_text(json.dumps({"answer": answer}))
            run("run", "build.py")
            output = (project / "output/page.png").read_bytes()
            assert output.startswith(b"\x89PNG\r\n\x1a\n")
            state = json.loads((project / "output/page.json").read_text())
            assert state["text"] == str(answer) and state["mode"] == "dynamic"
            hashes.append(hashlib.sha256(output).hexdigest())
        assert hashes[0] != hashes[1] and hashes[0] == hashes[2]

        (project / "status.py").write_text("raise SystemExit(7)\n")
        run("run", "status.py", status=7)
        selection = project / "firefox-purifier.json"
        selection.write_text('{"extensions": []}\n')
        result = subprocess.run(
            [str(cli), "prefetch"],
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert "selection changed" in result.stderr.lower(), result.stderr
        assert "lock --update" in result.stderr, result.stderr
    print(
        "Native rendering/source restoration, script status and stale lock checks passed"
    )


if __name__ == "__main__":
    main()
