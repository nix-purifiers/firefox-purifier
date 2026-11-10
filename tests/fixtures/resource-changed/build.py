"""Render project source with the real, locked Dark Reader extension."""

import http.server
import json
import threading
import time

browser = globals()["driver"]
project = globals()["project"]
output = globals()["output"]
answer = json.loads((project / "answer.json").read_text())["answer"]


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = (
            "<html><head><title>Locked browser</title><style>"
            "body {background:white;color:black} #answer {font-size:42px}"
            '</style></head><body><div id="answer">'
            + str(int(answer))
            + "</div></body></html>"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_arguments):
        pass


with http.server.HTTPServer(("127.0.0.1", 0), Handler) as server:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        browser.set_context("content")
        browser.get(f"http://127.0.0.1:{server.server_port}/")
        deadline = time.monotonic() + 30
        while True:
            state = browser.execute_script("""
return {mode:document.documentElement.getAttribute('data-darkreader-mode'),
        background:getComputedStyle(document.body).backgroundColor,
        text:document.getElementById('answer')?.textContent};
""")
            if state["mode"] == "dynamic":
                break
            if time.monotonic() > deadline:
                raise RuntimeError("Locked Dark Reader did not transform the page")
            time.sleep(0.05)
        assert state["text"] == str(answer)
        assert state["background"] != "rgb(255, 255, 255)"
        browser.execute_async_script("""
const done=arguments[0];
document.fonts.ready.then(()=>requestAnimationFrame(()=>requestAnimationFrame(done)));
""")
        browser.save_screenshot(str(output / "page.png"))
        (output / "page.json").write_text(json.dumps(state, sort_keys=True) + "\n")
    finally:
        server.shutdown()
        thread.join()
