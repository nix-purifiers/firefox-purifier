import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path

import lz4.block

source = Path(__file__).resolve().parents[1]
cli = Path(sys.argv[1]).resolve()
original_sdk = Path(sys.argv[2]).resolve()
resources = Path(sys.argv[3]).resolve()
sys.path.insert(0, str(source / "native"))
os.environ.update(
    FIREFOX_PURIFIER_FONTS=str(resources / "fonts.conf"),
    FIREFOX_PURIFIER_GECKODRIVER=str(resources / "bin/geckodriver"),
)
from firefox_purifier_driver import browser, native

fixture = source / "examples/minimal"
environment = Path(
    subprocess.run(
        [cli / "bin/firefox-purifier", "--project", fixture, "prefetch"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
)
identity = "addon@darkreader.org"
archive = environment / "archives" / f"{identity}.xpi"
with tempfile.TemporaryDirectory(prefix="firefox-cache-") as temporary:
    root = Path(temporary)
    profile = root / "profile"
    with browser(root / "seed", original_sdk, profile=profile) as driver:
        result = native(
            driver,
            """
 const {AddonManager}=ChromeUtils.importESModule('resource://gre/modules/AddonManager.sys.mjs');
 const file=Cc['@mozilla.org/file/local;1'].createInstance(Ci.nsIFile);file.initWithPath(args[0]);
 const install=await AddonManager.getInstallForFile(file);await install.install();
 return true;
 """,
            str(archive),
        )
    events = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            events.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args):
            pass

    with http.server.HTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            fake = root / "mutable-code"
            fake.mkdir()
            with zipfile.ZipFile(archive) as z:
                z.extractall(fake)
            manifest = json.loads((fake / "manifest.json").read_text())
            page = fake / manifest["background"]["page"]
            page.write_text(
                '<html><body><script src="purifier-probe.js"></script></body></html>'
            )
            (page.parent / "purifier-probe.js").write_text(
                "fetch("
                + json.dumps(
                    "http://127.0.0.1:" + str(server.server_port) + "/executed"
                )
                + ");"
            )
            database = profile / "extensions.json"
            startup = profile / "addonStartup.json.lz4"

            def forge():
                data = json.loads(database.read_text())
                addon = next(a for a in data["addons"] if a["id"] == identity)
                addon["rootURI"] = fake.as_uri() + "/"
                database.write_text(json.dumps(data))
                raw = startup.read_bytes()
                assert raw[:8] == b"mozLz40\0"
                data = json.loads(lz4.block.decompress(raw[8:]))
                data["app-profile"]["addons"][identity]["rootURI"] = fake.as_uri() + "/"
                startup.write_bytes(
                    raw[:8] + lz4.block.compress(json.dumps(data).encode())
                )

            forge()
            with browser(root / "original", original_sdk, profile=profile) as driver:
                deadline = time.monotonic() + 8
                while not events and time.monotonic() < deadline:
                    time.sleep(0.05)
                original = native(
                    driver,
                    "const {AddonManager}=ChromeUtils.importESModule('resource://gre/modules/AddonManager.sys.mjs');const a=await AddonManager.getAddonByID(args[0]);return {source:a.getResourceURI('').spec,active:a.isActive};",
                    identity,
                )
                assert events, original
            events.clear()
            forge()
            (profile / "user.js").write_text(
                'user_pref("extensions.logging.enabled",true);\n'
            )
            env = environment
            with browser(
                root / "locked", env / "sdk", environment=env, profile=profile
            ) as driver:
                time.sleep(1)
                locked = native(
                    driver,
                    "const {AddonManager}=ChromeUtils.importESModule('resource://gre/modules/AddonManager.sys.mjs');const a=await AddonManager.getAddonByID(args[0]);return {source:a?.getResourceURI('').spec,active:a?.isActive,builtins:(await AddonManager.getAllAddons()).filter(a=>a.isBuiltin||a.isSystem).map(a=>a.id)};",
                    identity,
                )
                assert (
                    not events
                    and locked["active"]
                    and locked["source"].startswith("jar:file:///nix/store/")
                ), locked
                assert "formautofill@mozilla.org" in locked["builtins"], locked
        finally:
            server.shutdown()
            thread.join()
print(
    "Original cached mutable code executes; locked native revalidation rejects its redirect"
)
