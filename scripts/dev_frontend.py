from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def run(command: list[str], cwd: Path) -> int:
    print(f"$ {' '.join(command)}", flush=True)
    return subprocess.call(command, cwd=cwd)


def main() -> int:
    npm = shutil.which("npm")
    if npm is None:
        print("npm was not found. Install Node.js first, then rerun this uv command.", file=sys.stderr)
        return 1

    node_modules = FRONTEND / "node_modules"
    if not node_modules.exists():
        install_command = "ci" if (FRONTEND / "package-lock.json").exists() else "install"
        install_code = run([npm, install_command], FRONTEND)
        if install_code != 0:
            return install_code

    return run([npm, "run", "dev"], FRONTEND)


if __name__ == "__main__":
    raise SystemExit(main())
