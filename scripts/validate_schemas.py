"""Validate both Bedrock action-group OpenAPI documents offline."""

import json
from pathlib import Path

from openapi_spec_validator import validate


def main():
    root = Path(__file__).resolve().parents[1]
    for path in sorted((root / "schemas").glob("*.json")):
        validate(json.loads(path.read_text()))
        print(f"Valid OpenAPI: {path.name}")


if __name__ == "__main__":
    main()
