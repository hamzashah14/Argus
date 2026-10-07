"""Build inventory-bound tools; deploy through infra.durable and infra.durable_ops."""

import argparse
import sys
from pathlib import Path

from infra import release
from infra.spec import load, log_groups, metric_catalog
from infra.verify import VerificationError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser("build", help="Build both inventory-bound read-only tools")
    build_parser.add_argument("--spec", type=Path, required=True)
    build_parser.add_argument("--output", type=Path, required=True)
    build_parser.add_argument("--wheelhouse", type=Path, required=True)
    args = parser.parse_args()
    try:
        from scripts.build_lambdas import FUNCTIONS, build

        spec = load(args.spec)
        args.output.mkdir(parents=True, exist_ok=True)
        release.write_json(args.output / "metric-catalog.json", metric_catalog(spec))
        release.write_json(args.output / "log-scope.json", log_groups(spec))
        build(
            FUNCTIONS,
            args.output,
            args.output / "metric-catalog.json",
            args.wheelhouse,
            args.output / "log-scope.json",
        )
        return 0
    except (VerificationError, ValueError, KeyError, OSError) as exc:
        print(f"Tool build failed ({type(exc).__name__}); no deployment occurred.", file=sys.stderr)
        if isinstance(exc, VerificationError):
            print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
