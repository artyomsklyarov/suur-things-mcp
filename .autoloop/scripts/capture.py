"""Capture the real dashboard with synthetic fixture data on an ephemeral port."""

import json
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
from conftest import build_things_db  # noqa: E402


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "screens"
    scenario = sys.argv[2] if len(sys.argv) > 2 else "normal"
    out = ROOT / ".autoloop/artifacts" / label
    out.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="suur-capture-") as directory:
        base = Path(directory)
        build_things_db(str(base / "main.sqlite"))
        os.environ.update(
            THINGS_DB=str(base / "main.sqlite"),
            SUUR_THINGS_CONFIG=str(base / "board.json"),
            SUUR_THINGS_TOKEN_FILE=str(base / "no-token"),
            THINGS_AUTH_TOKEN="",
        )
        import uvicorn
        from playwright.sync_api import sync_playwright

        from suur_things_mcp.dashboard import create_app

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(create_app(port), log_level="error"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        while not server.started:
            if not thread.is_alive():
                raise RuntimeError("fixture server failed")
            time.sleep(0.01)
        errors = []
        geometry = []
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                for name, width, height in [("desktop", 1440, 900), ("mobile", 390, 844)]:
                    page = browser.new_page(viewport={"width": width, "height": height})
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(
                        f"http://127.0.0.1:{port}" + ("?compact=1" if scenario == "compact" else ""),
                        wait_until="networkidle",
                    )
                    if scenario == "advanced":
                        for view, selector in [("matrix", ".matrix"), ("timeline", ".tl-wrap")]:
                            page.locator("#vt-" + view).click()
                            page.locator(selector).wait_for()
                            for theme in ["light", "dark"]:
                                page.evaluate("(t) => applyTheme(t)", theme)
                                page.wait_for_timeout(250)
                                page.screenshot(path=str(out / f"{name}-{view}-{theme}.png"))
                            page.locator("#vt-list").click()
                        page.close()
                        continue
                    if scenario == "project":
                        page.evaluate('() => go("#l/proj-empty")')
                        page.wait_for_timeout(300)
                    for theme in ["light", "dark"]:
                        page.evaluate("(t) => applyTheme(t)", theme)
                        page.wait_for_timeout(250)
                        page.screenshot(path=str(out / f"{name}-{theme}.png"))
                    if scenario == "project":
                        page.close()
                        continue
                    page.evaluate("() => openPrefs()")
                    page.wait_for_timeout(250)
                    page.screenshot(path=str(out / f"{name}-prefs.png"))
                    page.evaluate('() => closeOverlay("prefs-overlay")')
                    page.evaluate('() => go("#l/trash")')
                    page.wait_for_timeout(300)
                    page.screenshot(path=str(out / f"{name}-trash.png"))
                    geometry.append(
                        page.evaluate("""() => ({width:innerWidth, scroll:document.documentElement.scrollWidth,
                        main:document.querySelector('.main').getBoundingClientRect().width})""")
                    )
                    page.close()
                browser.close()
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            sock.close()
        (out / "report.json").write_text(json.dumps({"errors": errors, "geometry": geometry}, indent=2) + "\n")
        print(out)
        if errors:
            raise RuntimeError(errors)


if __name__ == "__main__":
    main()
