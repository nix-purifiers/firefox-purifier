import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

source = Path(__file__).resolve().parents[1]
cli, original, resources = (Path(value).resolve() for value in sys.argv[1:])
sys.path.insert(0, str(source / "native"))
from firefox_purifier_driver import browser

os.environ.update(
    FIREFOX_PURIFIER_FONTS=str(resources / "fonts.conf"),
    FIREFOX_PURIFIER_GECKODRIVER=str(resources / "bin/geckodriver"),
)
environment = Path(
    subprocess.run(
        [
            cli / "bin/firefox-purifier",
            "--project",
            source / "examples/minimal",
            "prefetch",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
)
results = []
with tempfile.TemporaryDirectory(prefix="firefox-temporary-") as temporary:
    root = Path(temporary)
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
            plugin = root / "unlocked"
            plugin.mkdir()
            (plugin / "manifest.json").write_text(
                json.dumps(
                    {
                        "manifest_version": 2,
                        "name": "Native temporary control",
                        "version": "1.0",
                        "browser_specific_settings": {
                            "gecko": {
                                "id": os.environ.get(
                                    "FIREFOX_TEST_ID", "purifier-unlocked@example.test"
                                )
                            }
                        },
                        "permissions": ["http://127.0.0.1/*"],
                        "background": {"scripts": ["background.js"]},
                    }
                )
            )
            for locked in [False, True]:
                label = "locked" if locked else "original"
                (plugin / "background.js").write_text(
                    "fetch("
                    + json.dumps(
                        "http://127.0.0.1:" + str(server.server_port) + "/" + label
                    )
                    + ");"
                )
                with browser(
                    root / label,
                    environment / "sdk" if locked else original,
                    environment=environment if locked else None,
                    network=False,
                ) as driver:
                    driver.set_context("chrome")
                    driver.set_script_timeout(60)
                    result = driver.execute_async_script(
                        """
      const filename=arguments[0],done=arguments[1];
      const {AddonManager}=ChromeUtils.importESModule('resource://gre/modules/AddonManager.sys.mjs');
      const file=Cc['@mozilla.org/file/local;1'].createInstance(Ci.nsIFile);file.initWithPath(filename);
      AddonManager.installTemporaryAddon(file).then(a=>done({id:a.id,active:a.isActive}),e=>done({error:String(e)}));
     """,
                        str(plugin),
                    )
                    deadline = time.monotonic() + 5
                    while "/" + label not in events and time.monotonic() < deadline:
                        time.sleep(0.05)
                    results.append(
                        {
                            "locked": locked,
                            "native": result,
                            "executed": "/" + label in events,
                        }
                    )
        finally:
            server.shutdown()
            thread.join()
print(json.dumps(results, indent=2))
assert results[0]["executed"], results
assert not results[1]["executed"], results
