"""PyInstaller entrypoint for Reweave.exe."""

import sys

from reweave.desktop import cli_main

if __name__ == "__main__":
    try:
        cli_main()
    except Exception:
        # PyInstaller's windowed traceback dialog must never interrupt headless
        # verification. Startup failure is observable as an unsuccessful exit.
        if "--headless" in sys.argv[1:]:
            raise SystemExit(1) from None
        raise
