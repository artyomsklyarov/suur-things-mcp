"""Run offline checks against disposable Things/config fixtures, never user data."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
from conftest import build_things_db  # noqa: E402


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "verification"
    artifact = ROOT / ".autoloop" / "artifacts" / f"{label}.txt"
    with tempfile.TemporaryDirectory(prefix="suur-verify-") as directory:
        base = Path(directory)
        build_things_db(str(base / "main.sqlite"))
        env = dict(
            os.environ,
            THINGS_DB=str(base / "main.sqlite"),
            SUUR_THINGS_CONFIG=str(base / "board.json"),
            SUUR_THINGS_TOKEN_FILE=str(base / "no-token"),
            THINGS_AUTH_TOKEN="",
        )
        checks = [
            [str(ROOT / ".venv/bin/ruff"), "check", "."],
            [sys.executable, "-m", "compileall", "-q", "src"],
            [sys.executable, "-m", "pytest", "-q"],
            ["uv", "build", "--offline", "--out-dir", str(base / "dist")],
        ]
        with artifact.open("w") as output:
            for cmd in checks:
                output.write("$ " + " ".join(cmd) + "\n")
                output.flush()
                result = subprocess.run(cmd, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT)
                output.write(f"Exit: {result.returncode}\n\n")
                output.flush()
                if result.returncode:
                    print(artifact.read_text())
                    return result.returncode
    print(artifact.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
