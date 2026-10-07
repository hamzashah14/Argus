"""Build the six durable pipeline Lambda packages from the verified wheelhouse."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.build_lambdas import PIPELINE_FUNCTIONS, ROOT, build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".build/pipeline")
    parser.add_argument("--wheelhouse", type=Path, required=True)
    args = parser.parse_args()
    build(
        PIPELINE_FUNCTIONS,
        args.output,
        ROOT / "config/metric-catalog.json",
        args.wheelhouse,
    )


if __name__ == "__main__":
    main()
