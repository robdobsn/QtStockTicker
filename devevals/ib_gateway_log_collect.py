#!/usr/bin/env python3
"""
Find IB Gateway / JTS logs and print recent, API-relevant lines — no manual hunting.

Run from anywhere (uses your home directory):
  uv run python devevals/ib_gateway_log_collect.py

By default the report is **short**: main launcher log tail + filtered “interesting” lines.
For the previous full dump (many files, long tails, broad grep):

  uv run python devevals/ib_gateway_log_collect.py --verbose
  # or: IB_LOG_COLLECT_VERBOSE=1

Optional:
  IB_LOG_COLLECT_ROOTS=/path1:/path2   # extra directories to scan (colon-separated)
  IB_LOG_TAIL_LINES                    # lines per tailed file (default 50 concise / 80 verbose)
  IB_LOG_MAX_FILES                     # max files to tail (default 1 concise / 8 verbose)

Exhaustive scan (also used by devevals/ib_connect_test.py on failure):
  IB_EXHAUSTIVE_MAX_FILES              # default 40
  IB_EXHAUSTIVE_MAX_LINES_PER_FILE     # default 50
  IB_CONNECT_TEST_NO_EXHAUSTIVE=1      # skip exhaustive pass when embedded in connect test
  IB_EXHAUSTIVE_INCLUDE_ROTATED=1      # include launcher.YYYYMMDD.log in keyword grep (noisy)
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

def _home_roots() -> list[Path]:
    h = Path.home()
    roots = [
        h / "Jts",
        h / "IBGateway",
        h / "Documents" / "IBGateway",
        h / ".ibgateway",
    ]
    extra = os.environ.get("IB_LOG_COLLECT_ROOTS", "").strip()
    if extra:
        for part in extra.split(":"):
            p = Path(part.strip()).expanduser()
            if p and p not in roots:
                roots.append(p)
    return roots


# Concise mode: focus on local API / socket / handshake (not every "api.ibkr.com" URL)
INTERESTING_CONCISE = re.compile(
    r"SocketListener|socket|SessionSocket|4001|4002|7496|7497|"
    r"disconnect|Disconnect|trusted|localhost|IsAPI|API port|"
    r"CLIENT_|NSConnect|PRELOGON|Handshake|refused|reject|EClient",
    re.IGNORECASE,
)

# Verbose mode: broader sweep
INTERESTING_VERBOSE = re.compile(
    r"API|Socket|socket|4001|4002|7496|7497|version|disconnect|"
    r"client|trusted|localhost|JTS-SocketListener|IsAPI",
    re.IGNORECASE,
)

# Drop chatty launcher lines that rarely explain *local* API failures
GREP_NOISE = re.compile(
    r"api\.ibkr\.com|GstatMessageMgr|AdManager|NEXT_AD|installer version|"
    r"java version\s*=|os version\s*=|Install4jAutoUpdateService",
    re.IGNORECASE,
)


def _launcher_log_since_last_start(lines: list[str]) -> tuple[list[str], int]:
    """
    IB Gateway appends runs in one launcher.log; take lines after the last
    '[JTS-Main] ... installer version' banner so grep/tail context is one session.
    """
    start = 0
    for i, line in enumerate(lines):
        if "JTS-Main" in line and "installer version" in line:
            start = i
    return lines[start:], start


def _is_installer_cruft(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    if ".install4j" in parts:
        return True
    n = path.name.lower()
    if n == "files.log":
        return True
    if n.endswith(".vmoptions") or n.endswith(".desktop") or n.endswith(".png"):
        return True
    if "cheatsheets" in parts and n == "spec.txt":
        return True
    # install4j launcher binary under Jts/ibgateway/<ver>/ibgateway
    if n == "ibgateway" and len(path.parts) >= 2 and path.parts[-2].isdigit():
        return True
    return False


def _iter_logish_files(root: Path, max_depth: int = 8) -> Iterator[Path]:
    """Yield files that look like logs or IB diagnostics; skip huge dirs."""
    skip_dir_names = {".git", "node_modules", "jars", "__pycache__"}
    if not root.is_dir():
        return

    def walk(d: Path, depth: int) -> Iterator[Path]:
        if depth > max_depth:
            return
        try:
            for entry in d.iterdir():
                try:
                    if entry.is_dir():
                        if entry.name in skip_dir_names:
                            continue
                        yield from walk(entry, depth + 1)
                    elif entry.is_file():
                        name = entry.name.lower()
                        if name.endswith(
                            (".log", ".txt", ".out", ".err")
                        ) or "log" in name:
                            yield entry
                        elif name.endswith(".ibgzenc") or "ibgateway" in name.lower():
                            yield entry
                except (OSError, PermissionError):
                    continue
        except (OSError, PermissionError):
            return

    yield from walk(root.resolve(), 0)


def _tail_lines(
    path: Path,
    max_lines: int,
    max_bytes: int = 25 * 1024 * 1024,
    *,
    launcher_current_session_only: bool = False,
) -> list[str]:
    """Read last max_lines from text file; skip binary / huge files.

    For ``launcher.log`` with ``launcher_current_session_only``, only lines after
    the last ``[JTS-Main] … installer version`` banner are kept, then the last
    *max_lines* of that slice — same scope as concise grep.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return []
    if size == 0:
        return []
    if size > max_bytes:
        return [f"[skip tail: file too large ({size} bytes): {path}]\n"]
    try:
        data = path.read_bytes()
    except OSError as e:
        return [f"[read error: {e}]\n"]
    if b"\0" in data[:4096]:
        return [f"[skip: appears binary: {path}]\n"]
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return [f"[skip: decode error: {path}]\n"]
    lines = text.splitlines()
    if launcher_current_session_only and path.name == "launcher.log":
        lines, _ = _launcher_log_since_last_start(lines)
    return lines[-max_lines:] if len(lines) > max_lines else lines


def _ss_lines_for_ports(ports: set[int]) -> list[str]:
    """Return `ss` LISTEN lines mentioning any of the given TCP ports."""
    need = tuple(f":{p}" for p in sorted(ports))
    for cmd in (["ss", "-ltnp"], ["ss", "-ltn"]):
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if r.returncode != 0 or not r.stdout.strip():
                continue
            out: list[str] = []
            for line in r.stdout.splitlines():
                if any(p in line for p in need):
                    out.append(line.rstrip())
            return out
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return []


def _print_ss_listen() -> None:
    print("=== Listening sockets (IB API ports 4001 / 4002 / 7496 / 7497) ===\n")
    lines = _ss_lines_for_ports({4001, 4002, 7496, 7497})
    if lines:
        for line in lines:
            print(line)
        print()
        return
    print(
        "(none of 4001/4002/7496/7497 found listening — Gateway may be off or use another port)\n",
    )


# Lines in launcher.log that may explain a dropped API client (beyond INTERESTING_CONCISE)
_LAUNCHER_FAILURE_EXTRA = re.compile(
    r"denied|unauthor|not\s+trusted|not\s+allowed|invalid\s+client|"
    r"Master\s+API|client\s*id|clientId|"
    r"JTS-SocketListener|ApiSocket|"
    r"connection.*closed|socket.*closed",
    re.IGNORECASE,
)

# IB launcher.log lines start with: 2026-04-04 23:17:54.123
_LAUNCHER_LINE_TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})")


def _launcher_line_datetime(line: str) -> datetime | None:
    m = _LAUNCHER_LINE_TS.match(line)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        return None


def _read_text_tail_bytes(path: Path, max_bytes: int = 512 * 1024) -> str | None:
    """Read tail of file as UTF-8; return None if binary or unreadable."""
    try:
        sz = path.stat().st_size
    except OSError:
        return None
    if sz == 0:
        return None
    try:
        with open(path, "rb") as f:
            if sz <= max_bytes + 2048:
                data = f.read()
            else:
                f.seek(max(0, sz - max_bytes))
                data = f.read()
    except OSError:
        return None
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


# Broad match for local API / policy / errors (exhaustive pass)
_EXHAUSTIVE_HINT = re.compile(
    r"API|socket|Socket|127\.0\.0\.1|localhost|"
    r"\b4001\b|\b4002\b|\b7496\b|\b7497\b|"
    r"client\s*id|clientId|Client\s*ID|EClient|handshake|serverVersion|"
    r"reject|denied|unauthor|trusted|listener|Listener|"
    r"disconnect|Disconnect|refused|"
    r"\b(ERROR|WARN|FATAL)\b.*(api|socket|client|connect)|"
    r"Throttl|pacing|Max\s+rate",
    re.IGNORECASE,
)


def _find_plain_logs_via_find(jts: Path, days: float = 3.0) -> list[Path]:
    """Use system ``find`` for every *.log / *.txt under Jts (fast on large trees)."""
    if not jts.is_dir():
        return []
    try:
        r = subprocess.run(
            [
                "find",
                str(jts),
                "-type",
                "f",
                "(",
                "-name",
                "*.log",
                "-o",
                "-name",
                "*.txt",
                "-o",
                "-name",
                "*.out",
                "-o",
                "-name",
                "*.err",
                ")",
                "-mtime",
                f"-{max(1, int(days))}",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return []
        out: list[Path] = []
        for line in r.stdout.splitlines():
            line = line.strip()
            if line:
                out.append(Path(line))
        return out
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []


def _collect_plaintext_log_paths(roots: list[Path]) -> list[tuple[float, Path]]:
    seen: set[Path] = set()
    scored: list[tuple[float, Path]] = []
    for root in roots:
        if not root.is_dir():
            continue
        if root.name == "Jts" or root.resolve().name == "Jts":
            for p in _find_plain_logs_via_find(root):
                try:
                    st = p.stat()
                except OSError:
                    continue
                if _is_installer_cruft(p):
                    continue
                rp = p.resolve()
                if rp in seen:
                    continue
                seen.add(rp)
                scored.append((st.st_mtime, rp))
        try:
            for f in _iter_logish_files(root, max_depth=12):
                if f.name.lower().endswith(".ibgzenc"):
                    continue
                if f.suffix.lower() not in (".log", ".txt", ".out", ".err"):
                    if "log" not in f.name.lower():
                        continue
                if _is_installer_cruft(f):
                    continue
                try:
                    st = f.stat()
                except OSError:
                    continue
                rp = f.resolve()
                if rp in seen:
                    continue
                seen.add(rp)
                scored.append((st.st_mtime, rp))
        except OSError:
            continue
    return scored


def _is_rotated_launcher_archive(path: Path) -> bool:
    """``launcher.YYYYMMDD.log`` — historical; noisy in exhaustive grep."""
    return bool(re.match(r"launcher\.\d{8}\.log$", path.name, re.I))


def _print_encrypted_vs_plain_banner(home: Path, failure_time: datetime) -> None:
    """When encrypted logs are fresher than launcher.log, say so loudly."""
    launcher = home / "Jts" / "launcher.log"
    lm: datetime | None = None
    try:
        if launcher.is_file():
            lm = datetime.fromtimestamp(launcher.stat().st_mtime)
    except OSError:
        pass
    enc: list[tuple[datetime, Path]] = []
    jts = home / "Jts"
    if jts.is_dir():
        try:
            for p in jts.glob("**/*.ibgzenc"):
                if not p.is_file():
                    continue
                try:
                    enc.append(
                        (datetime.fromtimestamp(p.stat().st_mtime), p),
                    )
                except OSError:
                    continue
        except OSError:
            pass
    if not enc:
        return
    enc.sort(key=lambda x: -x[0].timestamp())
    newest_dt, newest_p = enc[0]
    print("--- Encrypted vs plain-text (read this) ---\n", flush=True)
    if lm is not None and newest_dt > lm:
        print(
            f">>> Newest encrypted log ({newest_p.name}) is NEWER than launcher.log "
            f"({lm.isoformat(timespec='seconds')} vs {newest_dt.isoformat(timespec='seconds')}).\n"
            ">>> Gateway is appending session detail to *.ibgzenc, not launcher.log — "
            "your failed API connect will not show in plain text here.\n"
            ">>> Open IB Gateway → File → Logs (or the log viewer) for the real line.\n",
            flush=True,
    )
    delta_sec = abs((failure_time - newest_dt).total_seconds())
    if delta_sec <= 900:
        print(
            f">>> Closest encrypted log mtime is within {int(delta_sec)}s of this failure — "
            "evidence for this attempt is almost certainly there (not in .log files).\n",
            flush=True,
        )
    print(flush=True)


def _print_disconnect_reason_summary(paths: list[tuple[float, Path]]) -> None:
    """Extract DISCONNECT_* / reason= tokens from plain-text tails."""
    token_pat = re.compile(r"DISCONNECT_[A-Z][A-Z0-9_]+")
    reason_pat = re.compile(r"reason=([A-Za-z0-9_]+)")
    tokens: set[str] = set()
    sample_lines: list[str] = []

    for _mtime, path in paths[:8]:
        if path.name.lower() == "jts.ini":
            continue
        text = _read_text_tail_bytes(path, max_bytes=512 * 1024)
        if not text:
            continue
        for line in text.splitlines():
            for m in token_pat.finditer(line):
                tokens.add(m.group(0))
            for m in reason_pat.finditer(line):
                if m.group(1) not in ("null", "true", "false"):
                    tokens.add("reason=" + m.group(1))
            if re.search(
                r"DISCONNECT_|Authorization|not trusted|127\.0\.0\.1|SocketListener",
                line,
                re.I,
            ):
                s = line.rstrip()[:550]
                if s not in sample_lines:
                    sample_lines.append(s)
                if len(sample_lines) >= 15:
                    break
        if len(sample_lines) >= 15:
            break

    print("--- Plain-text disconnect / policy tokens (from recent file tails) ---\n", flush=True)
    if tokens:
        print(f"  Unique tokens: {', '.join(sorted(tokens)[:40])}\n", flush=True)
    else:
        print("  (no DISCONNECT_* strings in scanned tails)\n", flush=True)
    if sample_lines:
        print("  Sample lines:\n", flush=True)
        for s in sample_lines[:15]:
            print(f"    {s}", flush=True)
        print(flush=True)


def _sort_paths_for_failure(
    scored: list[tuple[float, Path]],
    failure_time: datetime,
) -> list[tuple[float, Path]]:
    def key(item: tuple[float, Path]) -> tuple[int, int, float]:
        mtime, p = item
        try:
            dt = datetime.fromtimestamp(mtime)
        except (OSError, ValueError, OverflowError):
            dt = datetime.min
        soon = abs((failure_time - dt).total_seconds()) < 7200
        name_hit = any(
            x in p.name.lower()
            for x in ("api", "message", "client", "socket", "gateway", "jts")
        )
        return (0 if soon else 1, 0 if name_hit else 1, -mtime)

    return sorted(scored, key=key)


def print_exhaustive_plaintext_log_scan(
    home: Path,
    failure_time: datetime,
    *,
    port: int,
) -> None:
    """
    Walk IB roots, read tails of every plausible plain-text log, grep for API clues.
    No manual path hunting. *.ibgzenc cannot be decoded here — listed separately.
    """
    max_files = int(os.environ.get("IB_EXHAUSTIVE_MAX_FILES", "40"))
    max_lines_out = int(os.environ.get("IB_EXHAUSTIVE_MAX_LINES_PER_FILE", "50"))
    ts = failure_time.isoformat(timespec="seconds")

    print(
        "\n"
        "=== EXHAUSTIVE plain-text scan (automated — no file picking) ===\n",
        flush=True,
    )
    print(
        f"Failure time for matching: {ts}  |  highlight port {port}\n",
        flush=True,
    )

    _print_encrypted_vs_plain_banner(home, failure_time)

    jts_ini = home / "Jts" / "jts.ini"
    if jts_ini.is_file():
        print(f"--- FULL {jts_ini} (first 200 lines) ---\n", flush=True)
        try:
            txt = jts_ini.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            print(f"(read error: {e})\n", flush=True)
        else:
            for i, line in enumerate(txt.splitlines()[:200], 1):
                print(f"  {i}: {line.rstrip()}", flush=True)
            n = len(txt.splitlines())
            if n > 200:
                print(f"  ... ({n - 200} more lines omitted)\n", flush=True)
            else:
                print(flush=True)

    roots = _home_roots()
    scored = _collect_plaintext_log_paths(roots)
    scored = _sort_paths_for_failure(scored, failure_time)
    include_rotated = os.environ.get("IB_EXHAUSTIVE_INCLUDE_ROTATED", "").lower() in (
        "1",
        "true",
        "yes",
    )
    rotated_n = sum(1 for _, p in scored if _is_rotated_launcher_archive(p))
    scored_for_grep = (
        scored
        if include_rotated
        else [x for x in scored if not _is_rotated_launcher_archive(x[1])]
    )
    if not include_rotated and rotated_n:
        print(
            f"(Exhaustive keyword pass skips {rotated_n} rotated "
            f"launcher.YYYYMMDD.log file(s); set IB_EXHAUSTIVE_INCLUDE_ROTATED=1 to include.)\n",
            flush=True,
        )

    print(
        f"--- Discovered {len(scored)} plain-text candidate file(s); "
        f"showing up to {max_files} (sorted: recent / name match) ---\n",
        flush=True,
    )
    for mtime, p in scored[: min(80, len(scored))]:
        try:
            sz = p.stat().st_size
        except OSError:
            sz = -1
        mts = datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
        print(f"  {mts}  {sz:>12} B  {p}", flush=True)
    if len(scored) > 80:
        print(f"  ... ({len(scored) - 80} more paths not listed)\n", flush=True)
    else:
        print(flush=True)

    jts_root = home / "Jts"
    if jts_root.is_dir():
        enc: list[tuple[float, Path]] = []
        try:
            for p in jts_root.glob("**/*.ibgzenc"):
                if not p.is_file():
                    continue
                try:
                    enc.append((p.stat().st_mtime, p))
                except OSError:
                    continue
        except OSError:
            pass
        enc.sort(key=lambda x: -x[0])
        if enc:
            print(
                "--- Encrypted Gateway logs (*.ibgzenc — not readable by this script) ---\n",
                flush=True,
            )
            for mtime, p in enc[:15]:
                try:
                    sz = p.stat().st_size
                except OSError:
                    sz = -1
                mts = datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
                print(f"  {mts}  {sz:>12} B  {p}", flush=True)
            print(
                "Open Gateway File → Logs in the UI, or request an IB support bundle — "
                "Python cannot decrypt these files.\n",
                flush=True,
            )

    _print_disconnect_reason_summary(scored_for_grep)

    print(
        "--- Keyword grep (last ~512KB or full file per path) ---\n",
        flush=True,
    )
    shown_files = 0
    for mtime, path in scored_for_grep:
        if shown_files >= max_files:
            break
        if path.name.lower() == "jts.ini":
            continue
        text = _read_text_tail_bytes(path)
        if text is None:
            print(f"{path}: [skipped: binary or unreadable]\n", flush=True)
            shown_files += 1
            continue
        plines = text.splitlines()
        hits: list[tuple[int, str]] = []
        for i, line in enumerate(plines):
            if GREP_NOISE.search(line) and "socket" not in line.lower():
                continue
            if _EXHAUSTIVE_HINT.search(line) or f":{port}" in line:
                hits.append((i + 1, line))
        if len(hits) > max_lines_out:
            hits = hits[-max_lines_out:]
        print(
            f"=== {path} (mtime {datetime.fromtimestamp(mtime).isoformat(timespec='seconds')}, "
            f"{len(hits)} matching lines in last ~512KB) ===\n",
            flush=True,
        )
        if not hits:
            print(
                "(no keyword hits in tail — file may still matter; try Gateway UI)\n",
                flush=True,
            )
        else:
            for rel_ln, line in hits:
                print(f"{path}:tail-line-{rel_ln}:{line.rstrip()[:600]}", flush=True)
            print(flush=True)
        shown_files += 1

    if not scored:
        print(
            "(no plain-text log candidates found under ~/Jts — is Gateway installed?)\n",
            flush=True,
        )


def print_ib_connect_failure_diagnostics(
    host: str,
    port: int,
    client_id: int,
    *,
    logs_only: bool = False,
) -> None:
    """
    After ibapi fails to complete connect(), print plain-text log excerpts from
    ~/Jts (same discovery logic as this module). Does not decode *.ibgzenc.

    Set ``logs_only=True`` when running without a connect attempt (same scans).
    """
    home = Path.home()
    now = datetime.now()
    ts = now.isoformat(timespec="seconds")
    title = (
        f"\n=== Log collection only (no API test) @ {ts} ===\n"
        if logs_only
        else f"\n=== Automatic log dig (API connect failed @ {ts}) ===\n"
    )
    print(title, flush=True)
    print(f"Attempted: {host}:{port} clientId={client_id}\n", flush=True)

    ports = {4001, 4002, 7496, 7497, port}
    print("--- ss: listeners on your port + standard API ports ---\n", flush=True)
    ss_lines = _ss_lines_for_ports(ports)
    if ss_lines:
        for line in ss_lines:
            print(line, flush=True)
    else:
        print(
            "(no matching LISTEN lines — wrong port, or `ss` missing, or nothing bound)\n",
            flush=True,
        )
    print(flush=True)

    jts_ini = home / "Jts" / "jts.ini"
    _grep_jts_ini(jts_ini)

    hunt = re.compile(
        INTERESTING_CONCISE.pattern + "|" + _LAUNCHER_FAILURE_EXTRA.pattern,
        re.IGNORECASE,
    )

    launcher = home / "Jts" / "launcher.log"
    if launcher.is_file():
        try:
            lmtime = datetime.fromtimestamp(launcher.stat().st_mtime)
        except OSError:
            lmtime = None
        try:
            text = launcher.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            print(f"--- launcher.log (read error: {e}) ---\n", flush=True)
        else:
            lines = text.splitlines()
            stale_file = lmtime is not None and (now - lmtime) > timedelta(minutes=5)
            if stale_file:
                print(
                    f"! launcher.log last modified {lmtime.isoformat(timespec='seconds')} "
                    f"— older than ~5 minutes before this failure. "
                    f"Plain text often stops when Gateway switches to encrypted *.ibgzenc; "
                    f"local API client attempts may not be echoed here at all.\n",
                    flush=True,
                )

            sess, off = _launcher_log_since_last_start(lines)
            buf: list[tuple[int, str]] = []
            for i in range(len(sess) - 1, -1, -1):
                line = sess[i]
                if GREP_NOISE.search(line):
                    continue
                if hunt.search(line):
                    buf.append((off + i + 1, line))
                    if len(buf) >= 50:
                        break
            buf.reverse()
            print(
                "--- launcher.log (current session; API / socket / policy-related lines) ---\n",
                flush=True,
            )
            if not buf:
                print(
                    "(no matching lines in plain launcher.log — see Gateway UI or *.ibgzenc)\n",
                    flush=True,
                )
            else:
                newest_in_buf: datetime | None = None
                for _, line in buf:
                    d = _launcher_line_datetime(line)
                    if d is not None and (newest_in_buf is None or d > newest_in_buf):
                        newest_in_buf = d
                if newest_in_buf is not None and (now - newest_in_buf) > timedelta(
                    minutes=5,
                ):
                    print(
                        f"! Newest matching line above is dated {newest_in_buf.isoformat(timespec='seconds')} "
                        f"— not near failure time {ts}. These lines are not from this connect attempt.\n",
                        flush=True,
                    )
                for ln, line in buf:
                    print(f"{launcher}:{ln}:{line.rstrip()[:500]}", flush=True)
                print(flush=True)

            raw_n = 40
            tail_raw = lines[-raw_n:] if len(lines) > raw_n else lines
            start_ln = len(lines) - len(tail_raw) + 1
            print(
                f"--- launcher.log (last {len(tail_raw)} lines, raw tail — look for timestamps near "
                f"{ts}) ---\n",
                flush=True,
            )
            for j, line in enumerate(tail_raw):
                print(f"{launcher}:{start_ln + j}:{line.rstrip()[:500]}", flush=True)
            print(flush=True)
    else:
        print(f"--- launcher.log: missing ({launcher}) ---\n", flush=True)

    if os.environ.get("IB_CONNECT_TEST_NO_EXHAUSTIVE", "").lower() not in (
        "1",
        "true",
        "yes",
    ):
        print_exhaustive_plaintext_log_scan(home, now, port=port)
    else:
        print(
            "(Exhaustive scan skipped: IB_CONNECT_TEST_NO_EXHAUSTIVE=1)\n",
            flush=True,
        )

    print(
        "Plain-text cannot include lines that only exist inside encrypted *.ibgzenc; "
        "the scan above lists those paths. Use Gateway File → Logs if you need IB’s UI.\n",
        flush=True,
    )


def _grep_jts_ini(path: Path) -> None:
    print(f"=== Snippet: {path} (log / socket / port / trusted) ===\n")
    if not path.is_file():
        print("(missing)\n")
        return
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"(read error: {e})\n")
        return
    pat = re.compile(
        r"(?i)(log|socket|port|trusted|api|client|localhost|ssl|message)",
    )
    shown = 0
    for i, line in enumerate(text.splitlines(), 1):
        if pat.search(line):
            print(f"  {i}: {line.rstrip()}")
            shown += 1
            if shown >= 40:
                print("  ... (truncated)")
                break
    if shown == 0:
        print("  (no matching keywords in first pass — file may use different keys)")
    print()


def _scan_interesting_lines(
    paths: list[Path],
    *,
    pattern: re.Pattern[str],
    max_hits: int,
    drop_noise: bool,
    from_end: bool = False,
) -> None:
    title = (
        "=== Filtered lines: local API / socket / ports (concise, newest matches) ===\n"
        if drop_noise
        else "=== Grep: API / socket / disconnect / port (recent files) ===\n"
    )
    print(title)
    hits = 0
    for path in paths:
        remaining = max_hits - hits
        if remaining <= 0:
            break
        try:
            if path.stat().st_size > 5 * 1024 * 1024:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        all_lines = text.splitlines()
        if from_end:
            all_lines, line_off = _launcher_log_since_last_start(all_lines)
            # Last N matching lines within the current session (avoids duplicate restarts)
            buf: list[tuple[int, str]] = []
            for i in range(len(all_lines) - 1, -1, -1):
                line = all_lines[i]
                line_no = i + 1
                if drop_noise and GREP_NOISE.search(line):
                    continue
                if pattern.search(line):
                    buf.append((line_off + line_no, line))
                    if len(buf) >= remaining:
                        break
            buf.reverse()
            for line_no, line in buf:
                print(f"{path}:{line_no}:{line.rstrip()[:500]}")
                hits += 1
        else:
            for i, line in enumerate(all_lines, 1):
                if drop_noise and GREP_NOISE.search(line):
                    continue
                if pattern.search(line):
                    print(f"{path}:{i}:{line.rstrip()[:500]}")
                    hits += 1
                    if hits >= max_hits:
                        break
            if hits >= max_hits:
                break
    if hits == 0:
        print(
            "(no keyword matches — try --verbose, or Gateway UI / File → Logs at failure time)",
        )
    print()


def _build_tail_list(
    scored: list[tuple[float, Path]],
    *,
    verbose: bool,
    max_tail_files: int,
    home: Path,
) -> list[Path]:
    launcher = home / "Jts" / "launcher.log"

    if not verbose:
        if launcher.is_file():
            return [launcher]
        for _, f in scored:
            if _is_installer_cruft(f):
                continue
            if f.suffix.lower() == ".log" or f.name.endswith(".log"):
                return [f]
        return []

    to_tail: list[Path] = []
    if launcher.is_file():
        to_tail.append(launcher)

    for _, f in scored:
        if f in to_tail:
            continue
        if _is_installer_cruft(f):
            continue
        if f.suffix.lower() == ".log" or f.name.endswith(".log"):
            to_tail.append(f)
        if len(to_tail) >= max_tail_files:
            break
    if len(to_tail) < max_tail_files:
        for _, f in scored:
            if f in to_tail or _is_installer_cruft(f):
                continue
            if f.suffix.lower() in (".txt", ".out", ".err"):
                to_tail.append(f)
            if len(to_tail) >= max_tail_files:
                break
    if len(to_tail) < max_tail_files:
        for _, f in scored:
            if f in to_tail or _is_installer_cruft(f):
                continue
            to_tail.append(f)
            if len(to_tail) >= max_tail_files:
                break
    return to_tail


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Collect IB Gateway / JTS log hints without hunting paths manually.",
    )
    ap.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Full report: many files, long tails, broad grep (old behavior).",
    )
    args = ap.parse_args()
    verbose = args.verbose or os.environ.get("IB_LOG_COLLECT_VERBOSE", "").strip() in (
        "1",
        "true",
        "yes",
    )

    tail_default = "80" if verbose else "50"
    tail_n = int(os.environ.get("IB_LOG_TAIL_LINES", tail_default))
    max_tail_env = os.environ.get("IB_LOG_MAX_FILES")
    if max_tail_env is not None:
        max_tail_files = int(max_tail_env)
    else:
        max_tail_files = 8 if verbose else 1

    home = Path.home()
    roots = _home_roots()
    print("=== IB Gateway log collector ===\n")
    print(f"Time: {datetime.now().isoformat(timespec='seconds')}")
    mode = "verbose (full)" if verbose else "concise (filtered)"
    print(f"Mode: {mode}")
    print(f"Scan roots: {', '.join(str(r) for r in roots)}\n")

    _print_ss_listen()

    jts_ini = home / "Jts" / "jts.ini"
    _grep_jts_ini(jts_ini)

    # Collect candidate files with mtimes
    scored: list[tuple[float, Path]] = []
    for root in roots:
        if not root.is_dir():
            print(f"(skip missing directory: {root})\n")
            continue
        for f in _iter_logish_files(root):
            try:
                mtime = f.stat().st_mtime
            except OSError:
                continue
            scored.append((mtime, f))

    scored.sort(key=lambda x: x[0], reverse=True)

    list_limit = 50 if verbose else 12
    print(
        "=== Recently modified log-like files (newest first) ===\n"
        if verbose
        else "=== Recent log-like files (installer noise omitted; use --verbose for full list) ===\n",
    )
    listed = 0
    for mtime, f in scored:
        if not verbose and _is_installer_cruft(f):
            continue
        ts = datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
        try:
            sz = f.stat().st_size
        except OSError:
            sz = -1
        print(f"  {ts}  {sz:>12} B  {f}")
        listed += 1
        if listed >= list_limit:
            break
    if listed == 0 and scored:
        print("  (all candidates filtered as installer noise — run with --verbose)")
    elif not scored:
        print("  (none found under known roots)")
    else:
        non_cruft = sum(1 for _, p in scored if not _is_installer_cruft(p))
        if not verbose and non_cruft > list_limit:
            print(
                f"  ... ({non_cruft - list_limit} more paths omitted; use --verbose)",
            )
    print()

    to_tail = _build_tail_list(scored, verbose=verbose, max_tail_files=max_tail_files, home=home)
    for f in to_tail:
        session_note = (
            f" (current Gateway session only; same cut as filtered grep)"
            if (not verbose and f.name == "launcher.log")
            else ""
        )
        print(f"=== Last {tail_n} lines: {f}{session_note} ===\n")
        lines = _tail_lines(
            f,
            tail_n,
            launcher_current_session_only=(not verbose and f.name == "launcher.log"),
        )
        for line in lines:
            print(line)
        print()

    if verbose:
        small_recent = []
        for _, f in scored[:25]:
            try:
                if f.stat().st_size <= 5 * 1024 * 1024:
                    small_recent.append(f)
            except OSError:
                continue
        _scan_interesting_lines(
            small_recent,
            pattern=INTERESTING_VERBOSE,
            max_hits=80,
            drop_noise=False,
        )
    else:
        grep_paths: list[Path] = []
        lp = home / "Jts" / "launcher.log"
        if lp.is_file():
            grep_paths.append(lp)
        else:
            for _, f in scored[:5]:
                if f.suffix.lower() == ".log" and not _is_installer_cruft(f):
                    grep_paths.append(f)
                    break
        _scan_interesting_lines(
            grep_paths,
            pattern=INTERESTING_CONCISE,
            max_hits=32,
            drop_noise=True,
            from_end=True,
        )

    print(
        "Done. If API failures are missing here, copy the **Gateway console / File → Logs** "
        "output around the failure time, or attach the daily ibgateway bundle from IB support.\n",
    )
    if not verbose:
        print("Tip: run with --verbose for multi-file tails and broad grep.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
