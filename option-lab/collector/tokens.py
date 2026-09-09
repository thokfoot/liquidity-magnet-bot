"""Fyers access-token lifecycle (server-side friendly).

Order tried:
    1.  Use tokens already in .env if present.
    2.  refresh_token grant at validate-authcode (two appIdHash formats; the
        ``-{app_type}:`` variant matches this account's legacy v2 flow).
    3.  Error with instructions to run the interactive auth-code flow once.

Needs FYERS_CLIENT_ID (+APP_TYPE), FYERS_SECRET_KEY, FYERS_REFRESH_TOKEN.
Writes new tokens back to .env atomically.
"""
from __future__ import annotations

import hashlib
import json
import logging
import urllib.parse
import urllib.request

from . import config as C

log = logging.getLogger(__name__)
AUTH_CODE_ENDPOINT = "https://api-t1.fyers.in/api/v3/validate-authcode"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def qualify_client_id(cid: str) -> str:
    """Ensure client_id carries the ``-{app_type}`` suffix the SDK expects."""
    if "-" in cid:
        return cid
    return f"{cid}-{C.FYERS_APP_TYPE}"


def _post(payload: dict) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(AUTH_CODE_ENDPOINT, data=body, headers={
        "Content-Type": "application/json", "User-Agent": USER_AGENT,
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - https
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:  # noqa: A001,BLE001 - surface as dict
        try:
            detail = exc.read().decode()
        except Exception:  # noqa: BLE001
            detail = ""
        return {"s": "error", "code": exc.code, "message": detail[:300]}


def try_refresh() -> dict | None:
    app_id = qualify_client_id(C.FYERS_CLIENT_ID)   # e.g. L0I73P22YA-100
    secret = C.FYERS_SECRET_KEY
    refresh = C.FYERS_REFRESH_TOKEN
    if not (app_id and secret and refresh):
        return None
    base = app_id.split("-")[0]
    app_type = C.FYERS_APP_TYPE
    hashes = [
        hashlib.sha256(f"{base}:{secret}".encode()).hexdigest(),
        hashlib.sha256(f"{base}-{app_type}:{secret}".encode()).hexdigest(),
        hashlib.sha256(f"{app_id}:{secret}".encode()).hexdigest(),
    ]
    seen = set()
    for h in hashes:
        if h in seen:
            continue
        seen.add(h)
        resp = _post({
            "grant_type": "refresh_token", "appIdHash": h, "refresh_token": refresh,
        })
        if resp.get("access_token"):
            return {"access_token": resp["access_token"],
                    "refresh_token": resp.get("refresh_token") or refresh}
        log.info("refresh hash %s... rejected: %s", h[:9], str(resp)[:160])
    return None


def write_env_var(name: str, value: str) -> None:
    if not C.ENV_PATH.exists():
        return
    lines = C.ENV_PATH.read_text(encoding="utf-8").splitlines()
    out, replaced = [], False
    for line in lines:
        if line.strip().startswith(f"{name}="):
            out.append(f"{name}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"{name}={value}")
    C.ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")
    log.info("updated %s in %s", name, C.ENV_PATH.name)


def try_autologin() -> dict | None:
    """Experimental v3 self-login: grant_type=pin (FY_ID+PIN+TOTP) -> new token pair.

    Uses FYERS_FY_ID / FYERS_PIN / FYERS_TOTP_KEY + appIdHash. Best-effort;
    any failure just falls through to the interactive auth-code flow.
    """
    fy_id, pin, totp_key = C.get("FYERS_FY_ID", ""), C.get("FYERS_PIN", ""), C.get("FYERS_TOTP_KEY", "")
    app_id = qualify_client_id(C.FYERS_CLIENT_ID)
    if not (fy_id and pin and totp_key and app_id and C.FYERS_SECRET_KEY):
        return None
    import urllib.request
    app_id_hash = hashlib.sha256(f"{app_id}:{C.FYERS_SECRET_KEY}".encode()).hexdigest()

    def post(path: str, payload: dict) -> dict:
        body = json.dumps(payload).encode()
        req = urllib.request.Request(f"https://api-t1.fyers.in/api/v3{path}",
                                     data=body, headers={
                                         "Content-Type": "application/json",
                                         "User-Agent": USER_AGENT}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - https
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:  # noqa: A001,BLE001
            try:
                return json.loads(exc.read().decode())
            except Exception:  # noqa: BLE001
                return {"s": "error", "code": exc.code, "message": "http"}

    r = post("/token", {"grant_type": "pin", "fyer_id": fy_id, "app_id_hash": app_id_hash,
                        "pin": pin, "totp_key": totp_key})
    token_id = ((r or {}).get("data") or {}).get("token_id") if r else None
    if not token_id:
        log.info("autologin pin step rejected: %s", masked(r))
        return None
    x = post("/validate-authcode", {"grant_type": "authorization_code", "appIdHash": app_id_hash,
                                    "code": token_id})
    if not x or not x.get("access_token"):
        log.info("autologin exchange rejected: %s", masked(x))
        return None
    return {"access_token": x["access_token"], "refresh_token": x.get("refresh_token") or token_id}


def masked(obj) -> str:
    s = str(obj)
    import re
    return re.sub(r"(eyJ[A-Za-z0-9_\-\.]+)", "<jwt>", s)[:220]


def ensure_valid_tokens() -> tuple[str, str]:
    """Return (client_id, access_token) that validate against the SDK; refresh if stale."""
    from fyers_apiv3.fyersModel import FyersModel

    cid = qualify_client_id(C.FYERS_CLIENT_ID)
    tok = C.FYERS_ACCESS_TOKEN

    if tok:
        probe = FyersModel(client_id=cid, token=tok, is_async=False,
                           log_path=None, log_level="ERROR")
        try:
            profile = probe.get_profile()
            if (profile or {}).get("s") == "ok":
                return cid, tok
            log.warning("access token stale (%s)", str(profile or {})[:120])
        except Exception as exc:  # noqa: BLE001
            log.warning("token probe error: %s", exc)

    # --- try refresh flow, then experimental pin+topt login, else interactive ---
    refreshed = try_refresh()
    if not refreshed:
        refreshed = try_autologin()
    if refreshed:
        write_env_var("FYERS_ACCESS_TOKEN", refreshed["access_token"])
        write_env_var("FYERS_REFRESH_TOKEN", refreshed["refresh_token"])
        log.info("token obtained via %s (client %s)",
                 "refresh" if (C.FYERS_REFRESH_TOKEN and refreshed["refresh_token"][:4] not in ("eyJh", "")) else "autologin", cid)
        return cid, refreshed["access_token"]

    raise RuntimeError(
        "FYERS token refresh failed. Manual once-per-(~28d) step:\n"
        "  cd C:\\Dev\\Dev\\Trading && python scripts/fyers_token.py\n"
        "and paste the auth code. Then restart the collector.")