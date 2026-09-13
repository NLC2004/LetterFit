from __future__ import annotations

import sys
import threading
import time
import webbrowser
from pathlib import Path

PORT = 8501


def _open_browser():
    time.sleep(2.5)
    webbrowser.open(f"http://localhost:{PORT}")


def main() -> None:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
        app_script = base / "app.py"
        if not app_script.exists():
            app_script = Path(sys._MEIPASS) / "app.py"  # type: ignore[attr-defined]
    else:
        app_script = Path(__file__).resolve().parent / "app.py"
    threading.Thread(target=_open_browser, daemon=True).start()
    from streamlit.web import cli as stcli

    sys.argv = [
        "streamlit",
        "run",
        str(app_script),
        "--server.headless=true",
        f"--server.port={PORT}",
        "--browser.gatherUsageStats=false",
    ]
    stcli.main()


if __name__ == "__main__":
    main()
