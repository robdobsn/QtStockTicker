#!/usr/bin/env python3
"""
Minimal IB API handshake test (same stack as StockTicker).

Optional TLS probe (IB_DIAG_PROBE_TLS=1) distinguishes:
  - TLS handshake OK  → API port expects TLS; plain ibapi cannot work until SSL is off for sockets.
  - TLS fails (EOF etc.) → port is plain TCP; "Use SSL" is not your issue; check trusted IPs, etc.

UI field names vary by IB Gateway version. This repo documents real dialogs under:
  devdocs/ibgateway-api-settings-linux.md
  devdocs/ibgateway-api-settings-windows-10-34-1c.md

Raw tools (nc) do not send the IB preamble; Gateway may log "version missing" for those.

Usage (from repo root):
  uv run python devevals/ib_connect_test.py
  IB_HOST=127.0.0.1 IB_PORT=4001 IB_CLIENT_ID=10 uv run python devevals/ib_connect_test.py

Optional TLS probe (sends TLS Client Hello; can add noise to Gateway logs):
  IB_DIAG_PROBE_TLS=1 uv run python devevals/ib_connect_test.py

Quiet logs:
  IB_CONNECT_TEST_DEBUG=1   # enable ibapi DEBUG

Short output (no long checklist on failure):
  IB_CONNECT_TEST_QUIET=1 uv run python devevals/ib_connect_test.py

On success, the script disconnects after a short wait; Gateway may log "Connection
terminated" for that client id — that is expected. Farm-related status codes (**2104**,
**2106**, **2107**, **2119**, **2158**: OK, connecting, HMDS inactive/on-demand, etc.)
are not failures; the default ibapi `EWrapper.error` logs them at ERROR — this script
suppresses that for those codes only.

After a failed handshake, the script runs an **exhaustive** plain-text scan (find + walk
~/Jts), full jts.ini, keyword grep on every candidate log — no manual file hunting.
To skip the heavy scan: IB_CONNECT_TEST_NO_EXHAUSTIVE=1
To skip all post-run output: IB_CONNECT_TEST_NO_LOGS=1

Logs only (no API connect — same discovery as after failure):
  uv run python devevals/ib_connect_test.py --logs-only
"""

from __future__ import annotations

import argparse
import logging
import os
import socket
import ssl
import sys
import threading
import time
from pathlib import Path

from ibapi.client import EClient
from ibapi.wrapper import EWrapper

# IB API delivers these via error(); farms OK / connecting / HMDS idle — not application failures.
_IB_INFO_STATUS_CODES = frozenset({2104, 2106, 2107, 2119, 2158})

# Sibling script: log paths / ss / launcher.log session slice
_deveval = Path(__file__).resolve().parent
if str(_deveval) not in sys.path:
    sys.path.insert(0, str(_deveval))
try:
    from ib_gateway_log_collect import print_ib_connect_failure_diagnostics
except ImportError:
    print_ib_connect_failure_diagnostics = None  # type: ignore[misc, assignment]

# Result of optional TLS probe: how to interpret the API port
TLS_SKIPPED = "skipped"
TLS_PORT_SPEAKS_TLS = "tls_ok"
TLS_PORT_PLAIN = "plain_tcp"
TLS_PROBE_ERROR = "error"


def _hints_failed_handshake(tls_kind: str) -> str:
    """Tailor hints after ibapi handshake fails; tls_kind from optional TLS probe."""
    common = (
        "\n"
        "Checklist (Edit → Global Configuration → API — see devdocs/ibgateway-api-settings-*.md):\n"
        "  General:\n"
        "    - Socket port matches IB_PORT (e.g. live vs paper; often 4001 vs 4002)\n"
        "    - Master API client ID: if set, your IB_CLIENT_ID must match; if blank, any id is allowed\n"
        "    - Turn on \"Create API message log file\" and read the line for this connection\n"
        "  Orders:\n"
        "    - \"Allow connections from localhost only\": if ON, connect using 127.0.0.1 (not only LAN IP)\n"
        "      If OFF, you must list the client machine under Trusted IPs\n"
        "  Trusted IPs:\n"
        "    - Include the address your client uses (e.g. 127.0.0.1 or a /24 or /16 range covering it)\n"
        "    - Remote/WSL/Docker: add that host's IP; loopback rules do not apply across VMs\n"
        "  Restart IB Gateway after changing API settings.\n"
        "\n"
        "Next steps (plain TCP but handshake still fails — Gateway is rejecting the session):\n"
        "  - Enable \"Create API message log file\" (General), retry this script, then search for the\n"
        "    matching timestamp under ~/Jts/ or ~/IBGateway/ (also main Gateway log window). The line\n"
        "    usually states why the client was dropped.\n"
        "  - If Trusted IPs already lists a range covering 127.0.0.1, try adding 127.0.0.1 explicitly,\n"
        "    or temporarily uncheck \"Allow connections from localhost only\" and rely on Trusted IPs\n"
        "    alone (some installs behave oddly with both).\n"
        "  - Confirm nothing else is bound to the same port and you are hitting the Gateway you configured\n"
        "    (one live vs paper instance; not a stale process).\n"
    )
    if tls_kind == TLS_PORT_SPEAKS_TLS:
        return (
            "\n"
            "TLS probe succeeded on this port — something on this port speaks TLS.\n"
            "Official Python ibapi is plain TCP. If your Gateway build has a separate "
            "\"Use SSL\" / encrypted API option, turn it off for plain clients or use a TLS-capable "
            "client library; then restart Gateway.\n"
            + common
        )
    if tls_kind == TLS_PORT_PLAIN:
        return (
            "\n"
            "TLS probe failed on this port — it behaves like plain TCP (normal for ibapi).\n"
            "Focus on Trusted IPs, \"Allow connections from localhost only\", socket port, and "
            "Master API client ID (see devdocs snapshots).\n"
            + common
        )
    # skipped or probe error
    return (
        "\n"
        "Handshake failed. If optional TLS probe was not run: set IB_DIAG_PROBE_TLS=1 to see "
        "whether the port expects TLS or plain TCP.\n"
        + common
    )


def _probe_tls_optional(host: str, port: int) -> tuple[str | None, str]:
    """
    Returns (line to print or None, tls_kind).
    tls_kind: TLS_SKIPPED, TLS_PORT_SPEAKS_TLS, TLS_PORT_PLAIN, or TLS_PROBE_ERROR
    """
    if os.environ.get("IB_DIAG_PROBE_TLS", "").lower() not in ("1", "true", "yes"):
        return None, TLS_SKIPPED
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    raw: socket.socket | None = None
    try:
        raw = socket.create_connection((host, port), timeout=5)
        ssl_sock = ctx.wrap_socket(raw, server_hostname=host)
        raw = None
        try:
            ver = ssl_sock.version() or "?"
        finally:
            ssl_sock.close()
        line = (
            f"IB_DIAG_PROBE_TLS: TLS handshake OK (protocol {ver}). "
            "This port accepts TLS — turn OFF 'Use SSL' for plain ibapi if Gateway is in SSL mode."
        )
        return line, TLS_PORT_SPEAKS_TLS
    except ssl.SSLError as e:
        if raw is not None:
            try:
                raw.close()
            except OSError:
                pass
        line = (
            f"IB_DIAG_PROBE_TLS: TLS failed ({e!r}) — port looks like plain TCP (expected for ibapi)."
        )
        return line, TLS_PORT_PLAIN
    except OSError as e:
        if raw is not None:
            try:
                raw.close()
            except OSError:
                pass
        return f"IB_DIAG_PROBE_TLS: {e}", TLS_PROBE_ERROR


def _quiet() -> bool:
    return os.environ.get("IB_CONNECT_TEST_QUIET", "").lower() in ("1", "true", "yes")


def _no_logs() -> bool:
    return os.environ.get("IB_CONNECT_TEST_NO_LOGS", "").lower() in ("1", "true", "yes")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="IB API handshake test + automated Gateway log discovery.",
    )
    ap.add_argument(
        "--logs-only",
        action="store_true",
        help="Do not connect; only run the same log / jts.ini / exhaustive scan as on failure.",
    )
    args = ap.parse_args()

    debug = os.environ.get("IB_CONNECT_TEST_DEBUG", "").lower() in ("1", "true", "yes")
    quiet = _quiet()
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if not debug:
        for name in ("ibapi", "ibapi.client", "ibapi.connection", "ibapi.decoder"):
            logging.getLogger(name).setLevel(logging.WARNING)

    host = os.environ.get("IB_HOST", "127.0.0.1")
    port = int(os.environ.get("IB_PORT", "4001"))
    client_id = int(os.environ.get("IB_CLIENT_ID", "10"))

    if args.logs_only:
        if print_ib_connect_failure_diagnostics is not None:
            print_ib_connect_failure_diagnostics(
                host=host,
                port=port,
                client_id=client_id,
                logs_only=True,
            )
        else:
            print(
                "ib_gateway_log_collect import failed; run from repo devevals/ directory.",
                file=sys.stderr,
            )
            return 2
        return 0

    tls_line, tls_kind = _probe_tls_optional(host, port)
    if tls_line and not quiet:
        print(tls_line, flush=True)

    class App(EWrapper, EClient):
        def __init__(self) -> None:
            EClient.__init__(self, self)

        def error(self, reqId: int, errorCode: int, errorString: str) -> None:
            if errorCode in _IB_INFO_STATUS_CODES:
                logging.getLogger("ib_connect_test").debug(
                    "IB status %s %s", errorCode, errorString
                )
                return
            EWrapper.error(self, reqId, errorCode, errorString)

    app = App()
    print(f"Connecting to {host}:{port} clientId={client_id} ...", flush=True)
    app.connect(host, port, client_id)
    ok = app.isConnected()
    print(f"connect() finished: isConnected={ok}", flush=True)
    if not ok:
        if quiet:
            print(
                "FAIL: Gateway closed the socket during API handshake (plain TCP). "
                "See devdocs/ibgateway-api-settings-*.md; check Gateway log at this timestamp; "
                "retry without IB_CONNECT_TEST_QUIET=1 for the full checklist.",
                flush=True,
            )
        else:
            print(_hints_failed_handshake(tls_kind), flush=True)
        if not _no_logs():
            if print_ib_connect_failure_diagnostics is not None:
                print_ib_connect_failure_diagnostics(
                    host=host,
                    port=port,
                    client_id=client_id,
                    logs_only=False,
                )
            else:
                print(
                    "(Log auto-digest unavailable: import ib_gateway_log_collect from devevals/.)",
                    flush=True,
                )
        return 1

    t = threading.Thread(target=app.run, daemon=True)
    t.start()
    time.sleep(2)
    print("Still connected after 2s:", app.isConnected(), flush=True)
    app.disconnect()
    time.sleep(0.5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
