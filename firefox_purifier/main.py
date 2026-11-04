"""FIREFOX's normal application workflow with a frozen native extension profile."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def public_url(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError("FIREFOX addon repositories must use public HTTPS URLs")
    return url


def selection(project):
    import re

    value = json.loads((project / "firefox-purifier.json").read_text())
    if set(value) != {"extensions"} or not isinstance(value["extensions"], list):
        raise ValueError("firefox-purifier.json needs a extensions list of native IDs")
    if any(
        not isinstance(id, str)
        or not re.fullmatch("[A-Za-z0-9{}][A-Za-z0-9@{}._-]*", id)
        for id in value["extensions"]
    ):
        raise ValueError("invalid native extension ID")
    if len(value["extensions"]) != len(set(value["extensions"])):
        raise ValueError("duplicate extension IDs")
    return value


def project_path(explicit):
    if explicit:
        return Path(explicit).resolve()
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / "firefox-purifier.json").exists() or (
            parent / "firefox-purifier.lock.json"
        ).exists():
            return parent
    return current


def validate(project, lock):
    data = json.loads(lock.read_text())
    if data.get("version") != 1 or data.get("purifier") != "firefox":
        raise ValueError("unsupported FIREFOX lock")
    if data.get("sdk") != os.environ["FIREFOX_PURIFIER_SDK"]:
        raise ValueError("FIREFOX SDK changed; run firefox-purifier lock --update")
    if data.get("selection") != selection(project):
        raise ValueError(
            "extension selection changed; run firefox-purifier lock --update"
        )
    return data


def realize(project, lock, target="environment", out_link=None):
    args = [
        "nix",
        "build",
        "--impure",
        "--file",
        os.environ["FIREFOX_PURIFIER_REALIZE"],
        "--argstr",
        "projectPath",
        str(project),
        "--argstr",
        "lockPath",
        str(lock),
        "--argstr",
        "target",
        target,
        "--json",
    ]
    args += ["--out-link", str(out_link)] if out_link else ["--no-link"]
    result = run(args, stdout=subprocess.PIPE, text=True)
    return Path(json.loads(result.stdout)[0]["outputs"]["out"])


def native_operation(root, request):
    request_file = root / "request.json"
    response = root / "response.json"
    request_file.write_text(json.dumps(request))
    run(
        [
            os.environ["FIREFOX_PURIFIER_PYTHON"],
            os.environ["FIREFOX_PURIFIER_NATIVE"] + "/firefox_purifier_helper.py",
            str(root / "session"),
            str(request_file),
            str(response),
        ],
        stdout=sys.stderr,
    )
    return json.loads(response.read_text())


def prefetch(url, name):
    return json.loads(
        run(
            [
                "nix",
                "store",
                "prefetch-file",
                "--json",
                "--name",
                name,
                public_url(url),
            ],
            stdout=subprocess.PIPE,
            text=True,
        ).stdout
    )


def capture(project, lock):
    requested = selection(project)
    with tempfile.TemporaryDirectory(prefix="firefox-purifier-") as temporary:
        root = Path(temporary)
        native = native_operation(
            root,
            {
                "action": "capture",
                "extensions": requested["extensions"],
                "root": str(root / "capture"),
            },
        )
        entries = []
        for entry in native["entries"]:
            fetched = prefetch(
                entry["url"],
                "firefox-addon-"
                + hashlib.sha256(entry["id"].encode()).hexdigest()[:12]
                + ".xpi",
            )

            if (
                hashlib.sha256(Path(fetched["storePath"]).read_bytes()).hexdigest()
                != entry["bytesSha256"]
            ):
                raise ValueError(
                    "Nix archive differs from the original Firefox download"
                )
            entries.append(
                {key: value for key, value in entry.items() if key != "bytesSha256"}
                | {"hash": fetched["hash"], "mirrors": []}
            )
        data = {
            "version": 1,
            "purifier": "firefox",
            "sdk": os.environ["FIREFOX_PURIFIER_SDK"],
            "selection": requested,
            "entries": entries,
            "native": {
                "metadata": native["metadata"],
                "repository": native["repository"],
            },
        }
        candidate = root / "firefox-purifier.lock.json"
        candidate.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        realize(project, candidate)
        lock.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", dir=lock.parent, delete=False
        ) as output:
            output.write(candidate.read_text())
            pending = Path(output.name)
        try:
            os.replace(pending, lock)
        finally:
            pending.unlink(missing_ok=True)


def prepared_environment(project, lock):
    data = validate(project, lock)
    state = project / ".firefox-purifier"
    identity = hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    roots = state / "environments"
    roots.mkdir(parents=True, exist_ok=True)
    environment = realize(project, lock, out_link=roots / identity)
    alias = state / "environment"
    if alias.exists() and not alias.is_symlink():
        raise ValueError("unexpected file at the managed Firefox environment link")
    with tempfile.TemporaryDirectory(dir=state) as temporary:
        link = Path(temporary) / "environment"
        link.symlink_to(environment)
        os.replace(link, alias)
    return state, environment


def native_exec(project, lock, arguments, command="firefox"):
    original = Path(os.environ["FIREFOX_PURIFIER_ORIGINAL"]) / "bin/firefox"
    if not lock.exists():
        print(
            "warning: no Firefox purifier lock; using ordinary, impure extension resolution",
            file=sys.stderr,
        )
        os.execve(original, [str(original), *arguments], os.environ.copy())
    state, environment = prepared_environment(project, lock)
    sys.path.insert(0, os.environ["FIREFOX_PURIFIER_NATIVE"])
    from firefox_purifier_gui import launch

    raise SystemExit(launch(state, environment, arguments))


def main():
    if os.environ.get("FIREFOX_PURIFIER_COMMAND") not in {None, "firefox-purifier"}:
        project = project_path(os.environ.get("FIREFOX_PURIFIER_PROJECT"))
        lock = Path(
            os.environ.get(
                "FIREFOX_PURIFIER_LOCK", project / "firefox-purifier.lock.json"
            )
        ).resolve()
        native_exec(project, lock, sys.argv[1:], os.environ["FIREFOX_PURIFIER_COMMAND"])
        return
    parser = argparse.ArgumentParser()
    parser.add_argument("--project")
    parser.add_argument("--lock")
    sub = parser.add_subparsers(dest="action", required=True)
    lock_parser = sub.add_parser("lock")
    lock_parser.add_argument("--update", action="store_true")
    sub.add_parser("prefetch")
    scripted = sub.add_parser("run")
    scripted.add_argument("script")
    for name in ["build", "bundle"]:
        sub.add_parser(name)
    publish = sub.add_parser("publish")
    publish.add_argument("--tag", required=True)
    execute = sub.add_parser("exec")
    execute.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    project = project_path(args.project or os.environ.get("FIREFOX_PURIFIER_PROJECT"))
    lock = Path(
        args.lock
        or os.environ.get(
            "FIREFOX_PURIFIER_LOCK", project / "firefox-purifier.lock.json"
        )
    ).resolve()
    if args.action == "run":
        state, environment = prepared_environment(project, lock)
        sys.path.insert(0, os.environ["FIREFOX_PURIFIER_NATIVE"])
        from firefox_purifier_run_project import run_project

        raise SystemExit(
            run_project(
                project,
                (project / args.script).resolve(),
                state / "run",
                environment,
                project / "output",
            )
        )

    if args.action == "lock" and args.update:
        capture(project, lock)
        return
    if args.action == "exec":
        arguments = (
            args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        )
        native_exec(project, lock, arguments)
        return
    validate(project, lock)
    if args.action == "lock":
        realize(project, lock)
    elif args.action == "prefetch":
        print(realize(project, lock))
    elif args.action in {"build", "bundle"}:
        print(
            realize(project, lock, "project" if args.action == "build" else "release")
        )
    elif args.action == "publish":
        release = realize(project, lock, "release")
        run(
            [
                os.environ.get("FIREFOX_PURIFIER_GH", "gh"),
                "release",
                "upload",
                args.tag,
                str(release / "firefox-project.tar.gz"),
                "--clobber",
            ]
        )


if __name__ == "__main__":
    try:
        main()
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"firefox-purifier: {error}", file=sys.stderr)
        sys.exit(1)
