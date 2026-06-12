#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    package_root = Path(__file__).resolve().parent / "src"
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))

    from glow_aws_deploy.cli import main as cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
