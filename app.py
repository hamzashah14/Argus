"""Customer-operated Kira web client. Run with: streamlit run app.py."""

import hmac
import os
import time
import uuid

import streamlit as st
from dotenv import load_dotenv

from kira import chat, identity
from kira import status as incident_status
from kira.config import AppConfig

load_dotenv()
settings = AppConfig.from_env()
st.set_page_config(page_title="Kira · Infrastructure investigations", page_icon="◈", layout="wide")
st.markdown(
    """<style>
.block-container { max-width: 1120px; padding-top: 4.5rem; padding-bottom: 5rem; }
[data-testid="stSidebar"] { border-right: 1px solid #243140; }
[data-testid="stChatMessage"] { border: 1px solid #243140; border-radius: 14px; }
.kira-label { color: #5eead4; font-size: .73rem; font-weight: 700; letter-spacing: .18em; margin-bottom: .6rem; }
.kira-title { font-size: clamp(2rem, 4vw, 3.3rem); line-height: 1.12; font-weight: 650; letter-spacing: -.04em; margin-bottom: .8rem; }
.kira-subtitle { color: #9fafc2; line-height: 1.6; max-width: 670px; margin-bottom: 1.7rem; }
.kira-brand { font-size: 1.7rem; font-weight: 750; letter-spacing: .1em; margin-bottom: .2rem; }
</style>""",
    unsafe_allow_html=True,
)


def clear_conversation():
    st.session_state.messages = []
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.last_prompt = ""
    st.session_state.connection_state = "Configured · not yet verified"


def sign_out():
    ticket = st.session_state.get("access_ticket")
    st.session_state.authenticated = False
    st.session_state.pop("auth_at", None)
    clear_conversation()
    if ticket:
        try:
            identity.Sessions().revoke(ticket)
        except identity.AccessDenied:
            # Preserve the reference so a later retry can revoke it. Do not
            # silently discard it or claim global logout during a storage outage.
            st.session_state.logout_failed = True
            return
    st.session_state.pop("access_ticket", None)
    st.session_state.pop("logout_failed", None)
    if identity.required() and st.user.get("is_logged_in", False):
        st.logout()


def authenticate():
    if identity.required():
        return
    password = st.session_state.get("workspace_password", "")
    accepted = hmac.compare_digest(password.encode(), settings.password.encode())
    st.session_state.authenticated = accepted
    st.session_state.login_error = not accepted
    st.session_state.pop("workspace_password", None)
    if accepted:
        st.session_state.auth_at = time.monotonic()
    else:
        time.sleep(1)


if "messages" not in st.session_state:
    clear_conversation()
if "attempts" not in st.session_state:
    st.session_state.attempts = []
if (
    not identity.required()
    and st.session_state.get("authenticated")
    and time.monotonic() - st.session_state.get("auth_at", 0) > chat.SESSION_SECONDS
):
    sign_out()
    st.session_state.session_expired = True

with st.sidebar:
    st.markdown('<div class="kira-brand">◈ KIRA</div>', unsafe_allow_html=True)
    st.caption("Your cloud. Your investigation.")
    st.divider()
    st.markdown("**Workspace**")
    st.caption("Customer-operated · AWS / CloudWatch")
    if st.session_state.get("authenticated"):
        st.button("New conversation", on_click=clear_conversation, width="stretch")
        st.button("Sign out", on_click=sign_out, width="stretch")
        st.divider()
        st.markdown("**Connection**")
        st.caption(st.session_state.connection_state if not settings.problems() else "Setup required")
        st.caption(f"Region: {settings.region or 'Not configured'}")
        st.caption(f"Runtime: {settings.runtime_target}")
        st.caption(f"Environment: {settings.environment}")
    st.divider()
    st.caption(
        "Investigations read the cloud resources allowed by your deployment. Review recommendations before making changes."
    )

st.markdown('<div class="kira-label">INFRASTRUCTURE INTELLIGENCE</div>', unsafe_allow_html=True)
st.markdown('<div class="kira-title">Investigate with context.</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="kira-subtitle">Connect an incident, its logs and its metrics. Kira helps you work from evidence toward an explanation—inside your own cloud.</div>',
    unsafe_allow_html=True,
)

if identity.required():
    # Native OIDC verifies state/nonce/signature. Never trust browser headers or
    # session_state's authenticated flag as an individual identity.
    st.session_state.authenticated = False
    if st.get_option("server.trustedUserHeaders") or not st.get_option("server.enableXsrfProtection"):
        clear_conversation()
        st.error("SSO requires XSRF protection and disabled trusted-header identity overrides.")
        st.stop()
    if st.session_state.get("logout_failed", False):
        st.error("Session revocation failed. Retry sign-out or ask the operator to revoke access.")
        st.button("Retry sign-out", on_click=sign_out)
        st.stop()
    if not st.user.get("is_logged_in", False):
        st.subheader("Sign in to your workspace")
        st.caption("Use your organization's identity provider and multi-factor authentication.")
        if st.button("Sign in with SSO", type="primary"):
            try:
                st.login()
            except Exception:
                st.error("SSO is not configured. Ask the deployment operator to check identity settings.")
        st.stop()
    try:
        if "access_ticket" not in st.session_state:
            st.session_state.access_ticket = identity.Sessions().issue(st.user.to_dict())
        access = identity.Sessions().authorize(st.session_state.access_ticket, "session", touch=False)
        if access["actor"] != identity.actor_id(st.user["iss"], st.user["sub"]):
            raise identity.AccessDenied()
        st.session_state.authenticated = True
    except (identity.AccessDenied, KeyError, TypeError):
        clear_conversation()
        st.error("Access is expired, revoked, or unavailable. Sign out and contact the deployment operator.")
        if st.button("Sign out from SSO"):
            sign_out()
        st.stop()

    if os.getenv("KIRA_STAGING_TICKET_FILE") and settings.environment == "staging":
        with st.expander("Operator staging canary"):
            st.caption(
                "Save your short-lived session to the private file configured by the local operator. This does not invoke a model."
            )
            if st.button("Save staging canary session"):
                try:
                    identity.Sessions().save_staging_ticket(
                        st.session_state.access_ticket,
                        os.environ["KIRA_STAGING_TICKET_FILE"],
                        st.get_option("server.address"),
                    )
                    st.success("Session saved to the operator's private file. Remove it after the canary.")
                except identity.AccessDenied:
                    st.error(
                        "Session export requires an investigator, a loopback staging UI and an owner-only directory."
                    )

if not identity.required() and len(settings.password) < 12:
    with st.container(border=True):
        st.subheader("Set up your workspace")
        st.info("Set APP_PASSWORD to at least 12 characters in your private .env file before signing in.")
        st.code(
            "cp .env.example .env\n# Set APP_PASSWORD and the verified runtime connection settings.",
            language="bash",
        )
        st.caption(
            "No cloud resources are created by opening this app. Deployment instructions are in the project README."
        )
    st.stop()

if not st.session_state.get("authenticated"):
    if st.session_state.pop("session_expired", False):
        st.info("Your session expired. Sign in again to continue.")
    with st.container(border=True):
        st.subheader("Sign in to your workspace")
        st.caption("Use the access password configured by the deployment operator.")
        with st.form("sign_in", clear_on_submit=True):
            st.text_input("Workspace password", type="password", max_chars=256, key="workspace_password")
            st.form_submit_button("Open workspace", type="primary", on_click=authenticate)
        if st.session_state.get("login_error"):
            st.error("The workspace password did not match.")
    st.stop()

requested_incident = st.query_params.get("incident")
if requested_incident:
    with st.container(border=True):
        st.subheader("Incident status")
        try:
            snapshot = (
                incident_status.load(requested_incident, access_ticket=st.session_state.access_ticket)
                if identity.required()
                else incident_status.load(requested_incident)
            )
            if snapshot is None:
                st.info("This incident was not found or has passed its retention period.")
            else:
                st.write({key: value for key, value in snapshot.items() if key != "report"})
                if snapshot.get("report"):
                    label = (
                        "Partial investigation checkpoint"
                        if snapshot.get("partial")
                        else "Investigation report"
                    )
                    st.text_area(label, snapshot["report"], height=280, disabled=True)
        except (ValueError, RuntimeError, OSError):
            st.warning("Incident status is unavailable. Ask the deployment operator to check storage access.")
        except Exception:
            # AWS client errors can include private infrastructure details.
            st.warning("Incident status is unavailable. Ask the deployment operator to check storage access.")

problems = settings.problems()
if problems:
    with st.container(border=True):
        st.subheader("Connect your runtime")
        st.info("Your workspace is ready for configuration. Runtime connectivity has not been checked.")
        for problem in problems:
            st.markdown(f"- {problem}")
        if settings.runtime_target == "classic":
            connection_example = (
                "RUNTIME_TARGET=classic\nBEDROCK_REGION=\nBEDROCK_AGENT_ID=\nBEDROCK_AGENT_ALIAS_ID="
            )
        else:
            connection_example = (
                f"RUNTIME_TARGET={settings.runtime_target}\nBEDROCK_REGION=\nBEDROCK_MODEL_ID=\n"
                "EXPECTED_ACCOUNT_ID=\nALLOWED_INSTANCE_IDS=\nRUNTIME_LIMITS=\nRUNTIME_RELEASE=\n"
            )
            connection_example += (
                "AGENTCORE_RUNTIME_ARN=\nAGENTCORE_ENDPOINT="
                if settings.runtime_target == "agentcore"
                else "LOGS_TOOL_ARN=\nMETRICS_TOOL_ARN="
            )
        st.code(connection_example, language="bash")
        st.caption(
            "Use your AWS profile, SSO session or workload role. The first investigation verifies that the configured agent can respond."
        )
    st.chat_input("Complete the connection settings to investigate", disabled=True)
    st.stop()

with st.expander("Connection details", expanded=False):
    st.write(
        {
            "Region": settings.region,
            "Runtime": settings.runtime_target,
            "Model": settings.model_id or "Configured by the legacy agent",
            "Endpoint": settings.agentcore_endpoint
            if settings.runtime_target == "agentcore"
            else settings.alias_id,
            "Environment": settings.environment,
            "Status": st.session_state.connection_state,
        }
    )
    st.caption(
        "Configured does not mean connected. A successful response verifies only that request, not overall cloud health."
    )

if not st.session_state.messages:
    st.markdown("**Start with a question**")
    cols = st.columns(3)
    for column, title, detail in zip(
        cols,
        ["Investigate an alert", "Explore a log gap", "Check resource pressure"],
        [
            "Include the instance, alarm and exact time.",
            "Compare activity before and after the incident.",
            "Correlate CPU, memory and disk with symptoms.",
        ],
    ):
        with column, st.container(border=True):
            st.markdown(f"**{title}**")
            st.caption(detail)
    st.caption("Example: What changed on i-0123456789abcdef0 around 2026-09-24T15:00:00+05:00?")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["content"]:
            st.markdown(message["content"])
        if message.get("status") in {"error", "partial"}:
            st.warning(message["message"])
            st.caption(f"{message['code']} · Reference {message['reference']}")
            if message["status"] == "partial":
                st.caption("Partial result · the investigation did not complete.")

now = time.monotonic()
st.session_state.attempts = chat.recent_attempts(st.session_state.attempts, now)
work_limit = len(st.session_state.attempts) >= chat.MAX_REQUESTS_PER_HOUR
scope_limit = identity.required() and access["role"] != "investigator"
if scope_limit:
    st.info("Your viewer role allows report access. Ask your operator for investigation access.")
history_limit = len(st.session_state.messages) >= chat.MAX_HISTORY_MESSAGES
if work_limit:
    st.info(
        "This browser session has reached its hourly investigation limit. Try again after earlier requests leave the one-hour window."
    )
if history_limit:
    st.info(
        "This conversation reached its history limit. Start a new conversation to reset the agent context."
    )
retry = False
if st.session_state.messages and st.session_state.messages[-1].get("status") in {"error", "partial"}:
    retry = st.button("Retry in a new conversation", disabled=work_limit or scope_limit)
prompt = st.chat_input(
    "Describe the incident. Include an instance ID and timestamp…",
    max_chars=chat.MAX_PROMPT_CHARS,
    disabled=work_limit or history_limit or scope_limit,
)
if retry:
    prompt = st.session_state.last_prompt
    clear_conversation()
if prompt and prompt.strip():
    st.session_state.attempts.append(time.monotonic())
    st.session_state.last_prompt = prompt
    with st.spinner("Reading evidence from your cloud…"):
        if identity.required():
            result = chat.invoke(
                prompt,
                st.session_state.session_id,
                settings,
                history=st.session_state.messages,
                access_ticket=st.session_state.access_ticket,
            )
        elif settings.runtime_target == "classic":
            result = chat.invoke(prompt, st.session_state.session_id, settings)
        else:
            result = chat.invoke(
                prompt, st.session_state.session_id, settings, history=st.session_state.messages
            )
    st.session_state.messages = chat.append_exchange(st.session_state.messages, prompt, result)
    st.session_state.connection_state = (
        "Last request succeeded" if result.status == "ok" else "Last request incomplete"
    )
    st.rerun()
