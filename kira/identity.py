"""Customer OIDC identities and revocable backend sessions; no request-trusted roles.

Only the UI passes already verified Streamlit OIDC claims to issue(). Backend
requests carry a signed opaque reference, never raw claims or an asserted role.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import time
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import boto3
from botocore.config import Config

ID = re.compile(r"[0-9a-f]{64}\Z")
SID = re.compile(r"[0-9a-f]{32}\Z")
IDLE_SECONDS = 900
ABSOLUTE_SECONDS = 28800


class AccessDenied(RuntimeError):
    def __init__(self):
        super().__init__("Identity or permission could not be verified.")


def required():
    return os.getenv("ENVIRONMENT", "development") != "development" or os.getenv("KIRA_AUTH_MODE") == "oidc"


def actor_id(issuer, subject):
    return hashlib.sha256(json.dumps([issuer, subject], separators=(",", ":")).encode()).hexdigest()


def audit(actor, action, outcome, instance=None):
    # Do not include claims, names, email, prompts, tickets or exception details.
    event = {"component": "access", "actor": actor, "action": action, "outcome": outcome}
    if instance:
        event["instance_id"] = instance
    print(json.dumps(event, separators=(",", ":")))


class Sessions:
    def __init__(self, *, table=None, clock=time.time, quotas=None):
        self.clock = clock
        self._table = table
        self._quotas = quotas

    def quotas(self):
        if self._quotas is None:
            from kira.quotas import Quotas

            self._quotas = Quotas(self.table(), clock=self.clock)
        return self._quotas

    def record(self, actor, action, outcome, instance=None):
        from kira.work_policy import configured

        now = int(self.clock())
        # The table is encrypted and TTL governed; no prompts/claims/tickets.
        event = {
            "component": "access",
            "actor": actor,
            "action": action,
            "outcome": outcome,
            "binding": self.policy()["binding"],
            "classification": "access-metadata",
            "ttl": now + configured()["audit_days"] * 86400,
        }
        if instance:
            event["instance_id"] = instance
        self.table().put_item(
            Item={
                "PK": "AUDIT#" + time.strftime("%Y-%m-%d", time.gmtime(now)),
                "SK": f"{now}#{secrets.token_hex(16)}",
                **event,
            }
        )
        audit(actor, action, outcome, instance)

    def policy(self):
        try:
            inline = os.getenv("KIRA_ACCESS_POLICY_JSON")
            filename = os.getenv("KIRA_ACCESS_POLICY_FILE")
            if bool(inline) == bool(filename):
                raise ValueError()
            if filename:
                path = Path(filename)
                if path.stat().st_size > 128000:
                    raise ValueError()
                inline = path.read_text()
            if len(inline.encode()) > 128000:
                raise ValueError()
            value = json.loads(inline)
            binding = [os.environ[k] for k in ("ENVIRONMENT", "EXPECTED_ACCOUNT_ID", "RUNTIME_RELEASE")]
            if (
                set(value) != {"version", "binding", "issuer", "audience"}
                or type(value["version"]) is not int
                or value["version"] != 1
                or value["binding"] != binding
                or not value["issuer"].startswith("https://")
                or not isinstance(value["audience"], str)
                or not value["audience"]
            ):
                raise ValueError()
            return value
        except Exception:
            raise AccessDenied() from None

    def grant(self, policy, actor):
        try:
            grant = (
                self.table()
                .get_item(Key={"PK": "IDENTITY#" + actor, "SK": "META"}, ConsistentRead=True)
                .get("Item")
            )
            epoch = grant["epoch"]
            if not (
                type(epoch) is int
                or (isinstance(epoch, Decimal) and epoch.is_finite() and epoch == epoch.to_integral_value())
            ):
                raise ValueError()
            grant = {**grant, "epoch": int(epoch)}
            ids = grant["instance_ids"]
            allowed = set(os.environ["ALLOWED_INSTANCE_IDS"].split(","))
            if (
                not grant
                or grant.get("binding") != policy["binding"]
                or grant["enabled"] is not True
                or grant["role"] not in {"viewer", "investigator"}
                or type(grant["epoch"]) is not int
                or grant["epoch"] < 1
                or not isinstance(ids, list)
                or not 1 <= len(ids) <= 100
                or any(
                    not isinstance(i, str) or not re.fullmatch(r"i-(?:[0-9a-f]{8}|[0-9a-f]{17})", i)
                    for i in ids
                )
                or len(set(ids)) != len(ids)
                or not set(ids) <= allowed
            ):
                raise ValueError()
            return grant
        except Exception:
            raise AccessDenied() from None

    def key(self):
        try:
            arn = os.getenv("KIRA_SESSION_KEY_ARN")
            direct = os.getenv("KIRA_SESSION_SIGNING_KEY")
            if bool(arn) == bool(direct):
                raise ValueError()
            if arn:
                version = os.environ["KIRA_SESSION_KEY_VERSION"]
                region, account = os.environ["BEDROCK_REGION"], os.environ["EXPECTED_ACCOUNT_ID"]
                if not re.fullmatch(
                    rf"arn:aws:secretsmanager:{re.escape(region)}:{re.escape(account)}:secret:[A-Za-z0-9/_-]+-[A-Za-z0-9]{{6}}",
                    arn,
                ):
                    raise ValueError()
                if not re.fullmatch(r"[A-Za-z0-9-]{32,64}", version):
                    raise ValueError()
                key = signing_key(arn, version, int(time.monotonic() // 60)).encode()
            else:
                key = direct.encode()
            if not 32 <= len(key) <= 4096:
                raise ValueError()
            return key
        except Exception:
            raise AccessDenied() from None

    def table(self):
        if self._table is None:
            try:
                self._table = boto3.resource(
                    "dynamodb",
                    region_name=os.environ["MONITOR_REGION"],
                    config=Config(connect_timeout=3, read_timeout=5, retries={"total_max_attempts": 1}),
                ).Table(os.environ["KIRA_SESSION_TABLE"])
            except Exception:
                raise AccessDenied() from None
        return self._table

    def sign(self, value):
        body = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
        signature = hmac.new(self.key(), body, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(signature + body).decode()

    def decode(self, ticket, policy):
        try:
            if not isinstance(ticket, str) or len(ticket) > 1024:
                raise ValueError()
            raw = base64.b64decode(ticket.encode(), altchars=b"-_", validate=True)
            if not hmac.compare_digest(raw[:32], hmac.new(self.key(), raw[32:], hashlib.sha256).digest()):
                raise ValueError()
            value = json.loads(raw[32:])
            if (
                set(value) != {"v", "sid", "actor", "binding"}
                or type(value["v"]) is not int
                or value["v"] != 1
                or not SID.fullmatch(value["sid"])
                or not ID.fullmatch(value["actor"])
                or value["binding"] != policy["binding"]
            ):
                raise ValueError()
            return value
        except Exception:
            raise AccessDenied() from None

    def issue(self, verified_claims):
        policy = self.policy()
        now = int(self.clock())
        actor = None
        try:
            claims = verified_claims
            issuer, subject = claims["iss"], claims["sub"]
            audience = claims["aud"]
            if isinstance(audience, list):
                if len(audience) != 1:
                    raise ValueError()
                audience = audience[0]
            if (
                issuer != policy["issuer"]
                or audience != policy["audience"]
                or not isinstance(subject, str)
                or not 1 <= len(subject) <= 512
                or type(claims["exp"]) is not int
                or claims["exp"] <= now
                or type(claims["auth_time"]) is not int
                or not 0 <= now - claims["auth_time"] < ABSOLUTE_SECONDS
                or not isinstance(claims.get("amr"), list)
                or "mfa" not in claims["amr"]
            ):
                raise ValueError()
            actor = actor_id(issuer, subject)
            grant = self.grant(policy, actor)
            self.quotas().admit(actor, "login")
            expiry = min(claims["exp"], claims["auth_time"] + ABSOLUTE_SECONDS)
            value = {"v": 1, "sid": secrets.token_hex(16), "actor": actor, "binding": policy["binding"]}
            ticket = self.sign(value)  # Validate secret before creating state.
            self.table().put_item(
                Item={
                    "PK": "SESSION#" + value["sid"],
                    "SK": "META",
                    "actor": actor,
                    "epoch": grant["epoch"],
                    "expires": expiry,
                    "idle_until": min(now + IDLE_SECONDS, expiry),
                    "ttl": expiry,
                },
                ConditionExpression="attribute_not_exists(PK)",
            )
        except Exception:
            try:
                self.record(actor, "login", "DENIED")
            except Exception:
                audit(actor, "login", "DENIED")
            raise AccessDenied() from None
        try:
            self.record(actor, "login", "ALLOWED")
        except Exception:
            # Issued-but-unreturned references expire; fail closed on audit outage.
            raise AccessDenied() from None
        return ticket

    def authorize(self, ticket, action, instance=None, *, touch=True):
        actor = None
        try:
            policy = self.policy()  # Both configuration and the authoritative grant are uncached.
            value = self.decode(ticket, policy)
            actor = value["actor"]
            grant = self.grant(policy, actor)
            key = {"PK": "SESSION#" + value["sid"], "SK": "META"}
            row = self.table().get_item(Key=key, ConsistentRead=True).get("Item")
            now = int(self.clock())
            if (
                not row
                or row["actor"] != actor
                or row["epoch"] != grant["epoch"]
                or row["expires"] <= now
                or row["idle_until"] <= now
                or action not in {"session", "chat", "report"}
                or (action == "chat" and grant["role"] != "investigator")
                or (action == "report" and instance is None)
                or (instance is not None and instance not in grant["instance_ids"])
            ):
                raise ValueError()
            if touch:
                self.table().update_item(
                    Key=key,
                    UpdateExpression="SET #idle=:idle",
                    ConditionExpression="#actor=:actor AND #epoch=:epoch AND #expires>:now AND #idle>:now",
                    ExpressionAttributeNames={
                        "#actor": "actor",
                        "#epoch": "epoch",
                        "#expires": "expires",
                        "#idle": "idle_until",
                    },
                    ExpressionAttributeValues={
                        ":idle": min(now + IDLE_SECONDS, int(row["expires"])),
                        ":actor": actor,
                        ":epoch": grant["epoch"],
                        ":now": now,
                    },
                )
        except Exception:
            try:
                self.record(actor, action if action in {"session", "chat", "report"} else "invalid", "DENIED")
            except Exception:
                audit(actor, "access", "DENIED")
            raise AccessDenied() from None
        if action != "session":
            try:
                self.record(actor, action, "ALLOWED", instance)
            except Exception:
                raise AccessDenied() from None
        return {"actor": actor, "role": grant["role"], "instance_ids": set(grant["instance_ids"])}

    def revoke(self, ticket):
        policy = self.policy()
        value = self.decode(ticket, policy)
        try:
            self.table().delete_item(Key={"PK": "SESSION#" + value["sid"], "SK": "META"})
        except Exception:
            audit(value["actor"], "logout", "DENIED")
            raise AccessDenied() from None
        try:
            self.record(value["actor"], "logout", "ALLOWED")
        except Exception:
            raise AccessDenied() from None

    def save_staging_ticket(self, ticket, filename, server_address):
        """Explicit local operator export; never a browser download or login bypass."""
        temporary = None
        try:
            if os.getenv("ENVIRONMENT") != "staging" or server_address not in {
                "127.0.0.1",
                "localhost",
                "::1",
            }:
                raise ValueError()
            access = self.authorize(ticket, "chat", touch=False)
            path = Path(filename).absolute()
            parent = path.parent.stat()
            if parent.st_uid != os.getuid() or parent.st_mode & 0o077:
                raise ValueError()
            with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as output:
                temporary = output.name
                os.fchmod(output.fileno(), 0o600)
                output.write(ticket + "\n")
            os.replace(temporary, path)
            temporary = None
            audit(access["actor"], "canary_export", "ALLOWED")
        except Exception:
            raise AccessDenied() from None
        finally:
            if temporary:
                Path(temporary).unlink(missing_ok=True)


@lru_cache(maxsize=8)
def signing_key(arn, version, cache_minute):
    """Pinned version, bounded one-minute cache; cache time is never authorization."""
    client = boto3.client(
        "secretsmanager",
        region_name=arn.split(":")[3],
        config=Config(connect_timeout=3, read_timeout=5, retries={"total_max_attempts": 1}),
    )
    response = client.get_secret_value(SecretId=arn, VersionId=version)
    if response.get("ARN") != arn or response.get("VersionId") != version:
        raise AccessDenied()
    value = response["SecretString"]
    if not isinstance(value, str) or not 32 <= len(value.encode()) <= 4096:
        raise AccessDenied()
    return value
