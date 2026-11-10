"""Offline smoke checks for the installed package in disposable CI systems."""

import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile


def main():
    with tempfile.TemporaryDirectory(prefix="beacon-smoke-") as directory:
        env = dict(os.environ, XDG_STATE_HOME=directory, LC_ALL="C")

        def run(*args, answer="", expected_code=0):
            result = subprocess.run(
                ["beacon", *args], input=answer, capture_output=True,
                text=True, env=env, timeout=60, check=False,
            )
            print(f"$ beacon {' '.join(args)}\n{result.stdout}{result.stderr}", flush=True)
            if result.returncode != expected_code:
                raise RuntimeError(f"Expected exit {expected_code}, got {result.returncode}")
            return result.stdout + result.stderr

        package_version = subprocess.check_output(
            ["dpkg-query", "-W", "-f", "${Version}", "beacon"], text=True, timeout=15,
        )
        version = run("--version").strip()
        if not re.fullmatch(r"Beacon v[0-9]+\.[0-9]+\.[0-9]+", version):
            raise RuntimeError("Unexpected installed CLI version")
        if package_version != f"{version.removeprefix('Beacon v')}-1":
            raise RuntimeError("Installed CLI and Debian package versions differ")
        help_text = run("--help")
        if "beacon.py" in help_text or "--untrack <package>" not in help_text:
            raise RuntimeError("Installed CLI help is missing the packaged untrack command")
        for option in ("--scan", "--repos", "--clean", "--local"):
            run(option)
        if "State      : Installed" not in run("beacon"):
            raise RuntimeError("Beacon did not discover its own installed package")
        if "No confirmed upstream associations." not in run("--tracked"):
            raise RuntimeError("Isolated tracking store should start empty")

        database = Path(directory) / "beacon" / "tracking.sqlite3"
        with sqlite3.connect(database) as db:
            db.execute(
                "INSERT INTO tracked_packages VALUES (?, ?, ?, ?)",
                ("beacon-smoke-absent", "all", 123, "Example/Project"),
            )
        if "Association not removed." not in run("--untrack", "beacon-smoke-absent", answer="\n"):
            raise RuntimeError("Untracking must default to declining removal")
        if "beacon-smoke-absent:all" not in run("--tracked"):
            raise RuntimeError("Declining removal lost the saved association")
        if "Association removed." not in run("--untrack", "beacon-smoke-absent", answer="yes\n"):
            raise RuntimeError("Explicit untracking did not remove the saved association")
        if "No confirmed upstream associations." not in run("--tracked"):
            raise RuntimeError("Untracked association remains in the store")
        if "No confirmed upstream" not in run("--untrack", "beacon-smoke-absent", expected_code=1):
            raise RuntimeError("Missing associations must produce a visible error")


if __name__ == "__main__":
    main()
