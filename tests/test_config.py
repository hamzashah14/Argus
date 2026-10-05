import json
import os
import subprocess
import sys

import pytest

from kira.config import ConfigError, DeploymentConfig
from tests.helpers import ROOT

BASE = {
    "EXPECTED_ACCOUNT_ID": "123456789012",
    "MONITOR_REGION": "eu-central-1",
    "BEDROCK_REGION": "eu-central-1",
}


def write_config(tmp_path, values=None):
    path = tmp_path / "config.env"
    path.write_text("".join(f"{key}={value}\n" for key, value in {**BASE, **(values or {})}.items()))
    return path


def test_required_only_config_exports_default_to_child(tmp_path):
    path = write_config(tmp_path)
    config = DeploymentConfig.load(path, "iam")
    assert config.AGENT_NAME == "aiops-assistant"
    run = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; "$KIRA_PYTHON" -c \'import json,os; print(json.dumps({"agent":os.environ["AGENT_NAME"],"maintenance":os.environ["MAINTENANCE_MODE"]}))\'',
            "test",
            str(ROOT / "scripts/common.sh"),
        ],
        env={**os.environ, "CONFIG_FILE": str(path), "KIRA_PYTHON": sys.executable},
        check=True,
        text=True,
        capture_output=True,
    )
    assert json.loads(run.stdout) == {"agent": "aiops-assistant", "maintenance": "false"}


@pytest.mark.parametrize(
    "values",
    [
        {"TYPO": "x"},
        {"EXPECTED_ACCOUNT_ID": "000000000000"},
        {"ENVIRONMENT": "prod"},
        {"CPU_THRESHOLD": "101"},
        {"MEM_THRESHOLD": "nan"},
        {"DISK_THRESHOLD": "0"},
        {"LOG_RETENTION_DAYS": "2"},
        {"LOG_GROUP_PREFIX": "/"},
        {"LOG_GROUP_PREFIX": "/aiops/"},
        {"AGENT_NAME": "bad name"},
        {"MONITOR_REGION": "$(touch nope)"},
        {"MONITOR_REGION": "cn-north-1"},
        {"ENABLE_PROCESS_ALARM": "yes"},
        {"INSTANCE_IDS": "i-bad"},
        {"CONTAINER_NAMES": "a,a"},
        {"TRIGGER_RESERVED_CONCURRENCY": "-1"},
        {"TRIGGER_RESERVED_CONCURRENCY": "0"},
        {"TRIGGER_RESERVED_CONCURRENCY": "00"},
        {"ENVIRONMENT": "production", "BEDROCK_AGENT_ALIAS_ID": "TSTALIASID"},
        {"LOG_CURSOR_SECRET": "short"},
        {"ALERT_EMAIL": "invalid"},
        {"BEDROCK_AGENT_ID": "bad"},
        {"METRIC_CATALOG_FILE": "missing-file.json"},
        {"DISK_PATH": "relative"},
    ],
)
def test_invalid_config_rejected(values, tmp_path):
    with pytest.raises(ConfigError):
        DeploymentConfig.load(write_config(tmp_path, values))


def test_maintenance_explicit_and_secret_not_in_repr(tmp_path):
    config = DeploymentConfig.load(
        write_config(
            tmp_path,
            {
                "TRIGGER_RESERVED_CONCURRENCY": "0",
                "MAINTENANCE_MODE": "true",
                "LOG_CURSOR_SECRET": "synthetic-long-secret-value-for-tests",
            },
        )
    )
    assert config.MAINTENANCE_MODE
    assert "synthetic-long-secret-value-for-tests" not in repr(config)


def test_unknown_keys_fail_before_cloud_command(tmp_path):
    marker = tmp_path / "aws-called"
    fake = tmp_path / "aws"
    fake.write_text(f'#!/bin/sh\ntouch "{marker}"\n')
    fake.chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(tmp_path) + os.pathsep + os.defpath,
        "CONFIG_FILE": str(write_config(tmp_path, {"UNKNOWN_FIELD": "x"})),
        "KIRA_PYTHON": sys.executable,
    }
    result = subprocess.run(["bash", str(ROOT / "setup-iam.sh")], env=env, text=True, capture_output=True)
    assert result.returncode != 0 and "Unknown configuration" in result.stderr
    assert not marker.exists()


def test_wrong_account_never_mutates(tmp_path):
    marker = tmp_path / "mutation"
    fake = tmp_path / "aws"
    fake.write_text(
        f'#!/bin/sh\nif [ "$1 $2" = "sts get-caller-identity" ]; then echo 999999999999; else touch "{marker}"; fi\n'
    )
    fake.chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(tmp_path) + os.pathsep + os.defpath,
        "CONFIG_FILE": str(write_config(tmp_path)),
        "KIRA_PYTHON": sys.executable,
    }
    result = subprocess.run(["bash", str(ROOT / "setup-iam.sh")], env=env, text=True, capture_output=True)
    assert result.returncode != 0 and "EXPECTED_ACCOUNT_ID" in result.stderr
    assert not marker.exists()


def test_export_values_are_data_not_executed(tmp_path):
    marker = tmp_path / "injected"
    value = f"$(touch {marker})"
    config = DeploymentConfig.load(write_config(tmp_path, {"NGINX_ERROR_FILTER_PATTERN": value}))
    result = subprocess.run(
        ["bash", "-c", config.exports() + '\nprintf "%s" "$NGINX_ERROR_FILTER_PATTERN"'],
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stdout == value and not marker.exists()


@pytest.mark.parametrize("field,value", [("statistic", []), ("unit", {})])
def test_malformed_catalog_values_produce_configuration_error(tmp_path, field, value):
    entry = {
        "id": "test",
        "instance_id": "i-0123456789abcdef0",
        "namespace": "CWAgent",
        "metric_name": "test",
        "statistic": "Sum",
        "dimensions": {},
        field: value,
    }
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps([entry]))
    with pytest.raises(ConfigError, match="METRIC_CATALOG_FILE"):
        DeploymentConfig.load(write_config(tmp_path, {"METRIC_CATALOG_FILE": str(catalog_path)}))


def test_relative_config_path_survives_root_change(tmp_path):
    write_config(tmp_path)
    result = subprocess.run(
        ["bash", "-c", 'source "$1"', "test", str(ROOT / "scripts/common.sh")],
        cwd=tmp_path,
        env={**os.environ, "CONFIG_FILE": "config.env", "KIRA_PYTHON": sys.executable},
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
