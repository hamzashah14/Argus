import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_lambda(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "lambda" / name / "lambda_function.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def body(envelope):
    import json

    return json.loads(envelope["response"]["responseBody"]["application/json"]["body"])
