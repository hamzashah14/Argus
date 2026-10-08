import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from kira import chat, execution, identity, runtime, status
from tests.helpers import ROOT

IID = "i-0123456789abcdef0"
OTHER = "i-1123456789abcdef0"
ISSUER = "https://identity.example.invalid"
ACTOR = identity.actor_id(ISSUER, "subject-1")
RELEASE = "a" * 64


class SessionTable:
    def __init__(self):
        self.rows = {}
        self.fail = False

    def put_item(self, Item, **kwargs):
        key = Item["PK"] if Item["SK"] == "META" else Item["PK"] + "/" + Item["SK"]
        if self.fail or key in self.rows:
            raise RuntimeError("storage rejected")
        self.rows[key] = copy.deepcopy(Item)

    def get_item(self, Key, **kwargs):
        if self.fail:
            raise RuntimeError("storage unavailable")
        assert kwargs["ConsistentRead"] is True
        return {"Item": copy.deepcopy(self.rows.get(Key["PK"]))}

    def update_item(self, Key, **kwargs):
        if self.fail or Key["PK"] not in self.rows:
            raise RuntimeError("revoked")
        row = self.rows[Key["PK"]]
        values = kwargs["ExpressionAttributeValues"]
        if row["expires"] <= values[":now"] or row["idle_until"] <= values[":now"]:
            raise RuntimeError("expired")
        row["idle_until"] = values[":idle"]

    def delete_item(self, Key):
        if self.fail:
            raise RuntimeError("unavailable")
        self.rows.pop(Key["PK"], None)


@pytest.fixture
def setup(monkeypatch, tmp_path):
    from kira.work_policy import DEFAULT

    monkeypatch.setenv("KIRA_WORK_POLICY", json.dumps(DEFAULT))
    monkeypatch.setenv("EXECUTION_PURPOSE", "chat")
    monkeypatch.setenv("KIRA_DIAGNOSTIC_POLICY", "diagnosis-v1")
    monkeypatch.setenv("KIRA_AUTH_MODE", "oidc")
    policy = {
        "version": 1,
        "binding": ["production", "123456789012", RELEASE],
        "issuer": ISSUER,
        "audience": "customer-ui",
    }
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy))
    for key, value in {
        "ENVIRONMENT": "production",
        "EXPECTED_ACCOUNT_ID": "123456789012",
        "RUNTIME_RELEASE": RELEASE,
        "KIRA_ACCESS_POLICY_FILE": str(path),
        "KIRA_SESSION_SIGNING_KEY": "fixture-" * 8,
        "ALLOWED_INSTANCE_IDS": IID + "," + OTHER,
        "RUNTIME_LIMITS": "{}",
    }.items():
        monkeypatch.setenv(key, value)
    now = [100000]
    table = SessionTable()
    table.rows["IDENTITY#" + ACTOR] = {
        "enabled": True,
        "epoch": 1,
        "role": "investigator",
        "instance_ids": [IID],
        "binding": policy["binding"],
    }
    sessions = identity.Sessions(table=table, clock=lambda: now[0], quotas=Mock())
    claims = {
        "iss": ISSUER,
        "sub": "subject-1",
        "aud": "customer-ui",
        "amr": ["mfa"],
        "auth_time": now[0],
        "exp": now[0] + 20000,
        "email": "private@example.invalid",
    }
    return SimpleNamespace(policy=policy, path=path, now=now, table=table, sessions=sessions, claims=claims)


@pytest.mark.parametrize(
    "claim,value",
    [
        ("iss", "https://wrong.invalid"),
        ("aud", "other-ui"),
        ("aud", ["customer-ui", "extra"]),
        ("sub", "unknown-user"),
        ("exp", 99999),
        ("exp", True),
        ("exp", "200000"),
        ("auth_time", 100001),
        ("auth_time", 1),
        ("amr", []),
        ("amr", "mfa"),
    ],
)
def test_unacceptable_identity_denied_before_state_creation(setup, claim, value):
    setup.claims[claim] = value
    with pytest.raises(identity.AccessDenied):
        setup.sessions.issue(setup.claims)
    assert not any(key.startswith("SESSION#") for key in setup.table.rows)


def test_session_audit_does_not_contain_personal_claims_or_ticket(setup, capsys):
    ticket = setup.sessions.issue(setup.claims)
    setup.sessions.authorize(ticket, "chat", IID)
    output = capsys.readouterr().out
    assert ACTOR in output and '"action":"chat"' in output
    assert "subject-1" not in output and "private@" not in output and ticket not in output


@pytest.mark.parametrize("change", ["role", "disable", "epoch", "remove", "scope", "binding"])
def test_policy_changes_immediately_affect_existing_ticket(setup, change):
    ticket = setup.sessions.issue(setup.claims)
    grant = setup.table.rows["IDENTITY#" + ACTOR]
    if change == "role":
        grant["role"] = "viewer"
    elif change == "disable":
        grant["enabled"] = False
    elif change == "epoch":
        grant["epoch"] += 1
    elif change == "remove":
        setup.table.rows.pop("IDENTITY#" + ACTOR)
    elif change == "scope":
        grant["instance_ids"] = [OTHER]
    elif change == "binding":
        setup.policy["binding"][2] = "b" * 64
    setup.path.write_text(json.dumps(setup.policy))
    with pytest.raises(identity.AccessDenied):
        setup.sessions.authorize(ticket, "chat", IID)


def test_viewer_can_read_own_report_but_cannot_investigate(setup):
    setup.table.rows["IDENTITY#" + ACTOR]["role"] = "viewer"
    setup.path.write_text(json.dumps(setup.policy))
    ticket = setup.sessions.issue(setup.claims)
    assert setup.sessions.authorize(ticket, "report", IID)["role"] == "viewer"
    with pytest.raises(identity.AccessDenied):
        setup.sessions.authorize(ticket, "chat")
    with pytest.raises(identity.AccessDenied):
        setup.sessions.authorize(ticket, "report", OTHER)


@pytest.mark.parametrize("elapsed", [identity.IDLE_SECONDS, identity.ABSOLUTE_SECONDS])
def test_expiry_does_not_depend_on_async_ttl_deletion(setup, elapsed):
    ticket = setup.sessions.issue(setup.claims)
    setup.now[0] += elapsed
    assert setup.table.rows
    with pytest.raises(identity.AccessDenied):
        setup.sessions.authorize(ticket, "chat")


def test_idle_extension_cannot_extend_token_expiry(setup):
    setup.claims["exp"] = setup.now[0] + 1000
    ticket = setup.sessions.issue(setup.claims)
    setup.now[0] += 899
    setup.sessions.authorize(ticket, "chat")
    setup.now[0] += 101
    with pytest.raises(identity.AccessDenied):
        setup.sessions.authorize(ticket, "chat")


def test_logout_revokes_ticket_on_another_session_store(setup):
    ticket = setup.sessions.issue(setup.claims)
    other_store = identity.Sessions(table=setup.table, clock=lambda: setup.now[0])
    setup.sessions.revoke(ticket)
    with pytest.raises(identity.AccessDenied):
        other_store.authorize(ticket, "chat")


@pytest.mark.parametrize("ticket", [None, "", "x" * 1025, "not-base64"])
def test_forged_ticket_rejected_without_storage_reads(setup, ticket):
    setup.sessions._table = Mock()
    with pytest.raises(identity.AccessDenied):
        setup.sessions.authorize(ticket, "chat")
    setup.sessions._table.get_item.assert_not_called()


def test_valid_ticket_cannot_be_modified(setup):
    ticket = setup.sessions.issue(setup.claims)
    with pytest.raises(identity.AccessDenied):
        setup.sessions.authorize(("A" if ticket[0] != "A" else "B") + ticket[1:], "chat")


def test_storage_unavailability_denies_session_and_logout(setup):
    ticket = setup.sessions.issue(setup.claims)
    setup.table.fail = True
    with pytest.raises(identity.AccessDenied):
        setup.sessions.authorize(ticket, "chat")
    with pytest.raises(identity.AccessDenied):
        setup.sessions.revoke(ticket)


def test_revocation_between_read_and_idle_update_cannot_resurrect_session(setup, monkeypatch):
    ticket = setup.sessions.issue(setup.claims)
    original = setup.table.get_item

    def revoked_after_read(**kwargs):
        response = original(**kwargs)
        if kwargs["Key"]["PK"].startswith("SESSION#"):
            setup.table.rows.pop(kwargs["Key"]["PK"])
        return response

    monkeypatch.setattr(setup.table, "get_item", revoked_after_read)
    with pytest.raises(identity.AccessDenied):
        setup.sessions.authorize(ticket, "chat")
    assert not any(key.startswith("SESSION#") for key in setup.table.rows)


def test_backend_chat_without_identity_cannot_create_model_or_tool_clients(setup):
    payload = {
        "version": 1,
        "release": RELEASE,
        "mode": "chat",
        "prompt": "Investigate",
        "history": [],
        "access_ticket": "forged",
    }
    with pytest.raises(identity.AccessDenied):
        execution.execute(payload)


def test_backend_request_cannot_assert_a_role_instead_of_ticket(setup):
    payload = {
        "version": 1,
        "release": RELEASE,
        "mode": "chat",
        "prompt": "Investigate",
        "history": [],
        "role": "investigator",
    }
    with pytest.raises(runtime.RuntimeStop, match="INVALID_EXECUTION_REQUEST"):
        execution.execute(payload)


def test_chat_denies_before_owned_runtime_invocation(setup, monkeypatch):
    settings = Mock()
    settings.problems.return_value = []
    denied = Mock(side_effect=identity.AccessDenied())
    monkeypatch.setattr(identity.Sessions, "authorize", denied)
    execute = Mock()
    monkeypatch.setattr(execution, "execute", execute)
    assert chat.invoke("Investigate", "test-session", settings).code == "ACCESS_DENIED"
    execute.assert_not_called()


def test_status_denies_unauthenticated_before_cloud_reads(setup):
    with pytest.raises(identity.AccessDenied):
        status.load("a" * 32)


def test_cross_scope_report_is_denied_before_s3(setup, monkeypatch):
    ticket = setup.sessions.issue(setup.claims)
    monkeypatch.setattr(identity, "Sessions", lambda: setup.sessions)
    monkeypatch.setenv("INCIDENT_TABLE", "fixture-ledger")
    monkeypatch.setenv("MONITOR_REGION", "eu-central-1")
    table = Mock()
    table.get_item.return_value = {"Item": {"instance_id": OTHER, "ttl": 2**31, "report_version": "v1"}}
    resource = Mock()
    resource.Table.return_value = table
    monkeypatch.setattr(status.boto3, "resource", lambda *a, **kw: resource)
    with pytest.raises(identity.AccessDenied):
        status.load("a" * 32, access_ticket=ticket)
    assert table.get_item.call_count == 1  # No evidence pointer or S3 read.


def test_execution_uses_only_user_inventory_and_rechecks_each_reservation(setup, monkeypatch):
    ticket = setup.sessions.issue(setup.claims)
    monkeypatch.setattr(identity, "Sessions", lambda: setup.sessions)
    captured = {}

    def tools(*args, **kwargs):
        captured.update(kwargs)
        return Mock()

    def run(*args, **kwargs):
        setup.table.rows["IDENTITY#" + ACTOR]["enabled"] = False
        setup.path.write_text(json.dumps(setup.policy))
        with pytest.raises(runtime.RuntimeStop, match="ACCESS_DENIED"):
            kwargs["reserve"]({"model_steps": 1})
        with pytest.raises(runtime.RuntimeStop, match="ACCESS_DENIED"):
            captured["access_guard"](IID)
        return {"complete": False, "text": "Stopped"}

    monkeypatch.setattr(execution, "tools", tools)
    monkeypatch.setattr(execution, "run", run)
    monkeypatch.setenv("BEDROCK_MODEL_ID", "fixture-model")
    monkeypatch.setenv("BEDROCK_REGION", "eu-central-1")
    result = execution.execute(
        {
            "version": 1,
            "release": RELEASE,
            "mode": "chat",
            "prompt": "Investigate",
            "history": [],
            "access_ticket": ticket,
        }
    )
    assert captured["allowed"] == {IID} and not result["complete"]


def test_production_shared_password_and_browser_flag_cannot_bypass_oidc(setup, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "fixture-workspace-password")
    test = AppTest.from_file(str(ROOT / "app.py"))
    test.session_state["authenticated"] = True
    test.run()
    assert not test.exception and not test.chat_input
    assert any(button.label == "Sign in with SSO" for button in test.button)
    assert not test.text_input


def staging(setup, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    setup.policy["binding"][0] = "staging"
    setup.path.write_text(json.dumps(setup.policy))


def test_staging_canary_export_is_private_and_contains_no_browser_download(
    setup, monkeypatch, tmp_path, capsys
):
    import streamlit

    staging(setup, monkeypatch)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    path = private / "canary.ticket"
    monkeypatch.setenv("KIRA_STAGING_TICKET_FILE", str(path))
    monkeypatch.setattr(identity, "Sessions", lambda: setup.sessions)
    monkeypatch.setattr(streamlit, "user", VerifiedUser({**setup.claims, "is_logged_in": True}))
    test = AppTest.from_file(str(ROOT / "app.py")).run()
    next(button for button in test.button if button.label == "Save staging canary session").click().run()
    assert not test.exception and path.read_text().strip() == test.session_state["access_ticket"]
    assert path.stat().st_mode & 0o777 == 0o600
    assert not test.get("download_button") and test.success
    assert test.session_state["access_ticket"] not in capsys.readouterr().out


@pytest.mark.parametrize("environment,address", [("production", "127.0.0.1"), ("staging", "0.0.0.0")])
def test_canary_export_cannot_be_enabled_in_production_or_on_public_bind(
    setup, monkeypatch, tmp_path, environment, address
):
    monkeypatch.setenv("ENVIRONMENT", environment)
    with pytest.raises(identity.AccessDenied):
        setup.sessions.save_staging_ticket("untrusted", str(tmp_path / "ticket"), address)
    assert not (tmp_path / "ticket").exists()


def test_viewer_and_unsafe_directory_cannot_export_ticket(setup, monkeypatch, tmp_path):
    staging(setup, monkeypatch)
    ticket = setup.sessions.issue(setup.claims)
    path = tmp_path / "ticket"
    tmp_path.chmod(0o755)
    with pytest.raises(identity.AccessDenied):
        setup.sessions.save_staging_ticket(ticket, str(path), "127.0.0.1")
    tmp_path.chmod(0o700)
    setup.table.rows["IDENTITY#" + ACTOR]["role"] = "viewer"
    with pytest.raises(identity.AccessDenied):
        setup.sessions.save_staging_ticket(ticket, str(path), "127.0.0.1")
    assert not path.exists()


class VerifiedUser(dict):
    def to_dict(self):
        return dict(self)


def test_sso_session_uses_durable_identity_and_clears_history_on_revocation(setup, monkeypatch):
    import streamlit

    monkeypatch.setattr(identity, "Sessions", lambda: setup.sessions)
    monkeypatch.setattr(streamlit, "user", VerifiedUser({**setup.claims, "is_logged_in": True}))
    test = AppTest.from_file(str(ROOT / "app.py"))
    test.run()
    assert not test.exception and test.session_state["authenticated"]
    test.session_state["messages"] = [{"role": "user", "content": "private question"}]
    setup.table.rows["IDENTITY#" + ACTOR]["enabled"] = False
    test.run()
    assert not test.exception and not test.session_state["authenticated"]
    assert test.session_state["messages"] == [] and not test.chat_input


def test_logout_failure_retains_reference_for_retry_and_blocks_workspace(setup, monkeypatch):
    import streamlit

    monkeypatch.setattr(identity, "Sessions", lambda: setup.sessions)
    monkeypatch.setattr(streamlit, "user", VerifiedUser({**setup.claims, "is_logged_in": True}))
    logout = Mock()
    monkeypatch.setattr(streamlit, "logout", logout)
    test = AppTest.from_file(str(ROOT / "app.py"))
    test.run().run()
    ticket = test.session_state["access_ticket"]
    setup.table.fail = True
    next(button for button in test.button if button.label == "Sign out").click().run()
    assert not test.exception and not test.chat_input
    assert test.session_state["access_ticket"] == ticket
    assert test.session_state["logout_failed"] and test.session_state["messages"] == []
    logout.assert_not_called()
    setup.table.fail = False
    next(button for button in test.button if button.label == "Retry sign-out").click().run()
    logout.assert_called_once()
    with pytest.raises(identity.AccessDenied):
        setup.sessions.authorize(ticket, "chat")


def test_runtime_rechecks_access_before_count_tokens_or_converse(monkeypatch):
    client = Mock()
    guard = Mock(side_effect=runtime.RuntimeStop("ACCESS_DENIED"))
    result = runtime.run(
        "Question",
        model_id="fixture-model",
        region="eu-central-1",
        tools=Mock(),
        reserve=Mock(),
        limits=runtime.Limits(),
        deadline=2**31,
        client=client,
        access_guard=guard,
    )
    assert not result["complete"] and result["code"] == "ACCESS_DENIED"
    client.count_tokens.assert_not_called()
    client.converse.assert_not_called()


@pytest.mark.parametrize(
    "option,value", [("server.trustedUserHeaders", {"x-user": "sub"}), ("server.enableXsrfProtection", False)]
)
def test_native_identity_cannot_be_overridden_with_trusted_headers(setup, monkeypatch, option, value):
    import streamlit

    original = streamlit.get_option
    monkeypatch.setattr(streamlit, "get_option", lambda key: value if key == option else original(key))
    test = AppTest.from_file(str(ROOT / "app.py"))
    test.session_state["authenticated"] = True
    test.run()
    assert not test.exception and not test.chat_input
    assert any("XSRF protection" in item.value for item in test.error)


def test_real_dynamodb_number_deserialization_accepts_integer_epoch(setup):
    from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

    serializer, deserializer = TypeSerializer(), TypeDeserializer()
    key = "IDENTITY#" + ACTOR
    setup.table.rows[key] = {
        k: deserializer.deserialize(serializer.serialize(v)) for k, v in setup.table.rows[key].items()
    }
    ticket = setup.sessions.issue(setup.claims)
    assert setup.sessions.authorize(ticket, "chat", IID)["actor"] == ACTOR


@pytest.mark.parametrize("epoch", [True, 0, "1", 1.5])
def test_invalid_revocation_epoch_cannot_issue_session(setup, epoch):
    setup.table.rows["IDENTITY#" + ACTOR]["epoch"] = epoch
    with pytest.raises(identity.AccessDenied):
        setup.sessions.issue(setup.claims)
    assert not any(key.startswith("SESSION#") for key in setup.table.rows)


@pytest.mark.parametrize("key", ["", "too-short"])
def test_invalid_signing_key_cannot_issue_session(setup, monkeypatch, key):
    monkeypatch.setenv("KIRA_SESSION_SIGNING_KEY", key)
    with pytest.raises(identity.AccessDenied):
        setup.sessions.issue(setup.claims)
    assert not any(key.startswith("SESSION#") for key in setup.table.rows)
