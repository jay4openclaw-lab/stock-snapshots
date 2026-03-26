#!/usr/bin/env python3
"""
check_reconnect_errors.py

Behavior:
- Called when the user invokes the assistant after some idle time.
- If the time since the last user call is >= 3600 seconds (1 hour), scan gateway.err.log
  and sessions JSONL for error patterns (400 invalid_request_body and validation errors).
- If errors found since the previous call time, return a small report indicating errors found
  and the public URL for the detailed error report (if available).
- Always update the last-call timestamp file (~/.openclaw/last_user_call.json) to now.

Usage: python3 check_reconnect_errors.py
Output (stdout): JSON with keys: {"idle_seconds": int, "checked_since": str_or_null,
    "errors_found": bool, "error_count": int, "report_url": str_or_null}

"""
import os
import re
import json
from datetime import datetime, timezone, timedelta

HOME = os.path.expanduser('~')
LAST_CALL_FILE = os.path.join(HOME, '.openclaw', 'last_user_call.json')
GATEWAY_ERR_LOG = os.path.join(HOME, '.openclaw', 'logs', 'gateway.err.log')
SESSIONS_DIR = os.path.join(HOME, '.openclaw', 'agents', 'main', 'sessions')
REPORT_URL = 'https://jay4openclaw-lab.github.io/stock-snapshots/latest_errors.html'
IDLE_THRESHOLD = 3600  # seconds (1 hour)

# helper: parse ISO timestamps from a line
iso_re = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+\-]\d{2}:\d{2}))")

now = datetime.now(timezone.utc)
last_ts = None
if os.path.exists(LAST_CALL_FILE):
    try:
        with open(LAST_CALL_FILE, 'r') as f:
            j = json.load(f)
            last_ts = datetime.fromisoformat(j.get('last_call'))
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)
    except Exception:
        last_ts = None

idle_seconds = None
if last_ts is None:
    idle_seconds = None
else:
    idle_seconds = int((now - last_ts).total_seconds())

# Decide if we should scan
should_scan = False
if last_ts is None:
    should_scan = True
else:
    should_scan = (now - last_ts).total_seconds() >= IDLE_THRESHOLD

errors_found = False
error_count = 0
checked_since = None

if should_scan:
    # set checked_since to last_ts if present else 'beginning'
    checked_since = last_ts.isoformat() if last_ts else 'beginning'
    # scan gateway.err.log for patterns
    patterns = [r'invalid_request_body', r'"validation_error"', r'400 \{"message"', r'heading_2.rich_text']
    try:
        if os.path.exists(GATEWAY_ERR_LOG):
            with open(GATEWAY_ERR_LOG, 'r', errors='ignore') as f:
                for line in f:
                    if any(re.search(p, line) for p in patterns):
                        # optional: only count lines after last_ts if last_ts available
                        if last_ts:
                            m = iso_re.search(line)
                            if m:
                                try:
                                    t = datetime.fromisoformat(m.group(1))
                                    # normalize tz
                                    if t.tzinfo is None:
                                        t = t.replace(tzinfo=timezone.utc)
                                except Exception:
                                    t = None
                                if t and t <= last_ts:
                                    continue
                        error_count += 1
        # also scan recent sessions JSONL for errorMessage patterns
        if os.path.isdir(SESSIONS_DIR):
            for fn in os.listdir(SESSIONS_DIR):
                if not fn.endswith('.jsonl'):
                    continue
                full = os.path.join(SESSIONS_DIR, fn)
                try:
                    with open(full, 'r', errors='ignore') as f:
                        for line in f:
                            if 'invalid_request_body' in line or '"message":"","code":"invalid_request_body"' in line:
                                # same time filtering
                                if last_ts:
                                    m = iso_re.search(line)
                                    if m:
                                        try:
                                            t = datetime.fromisoformat(m.group(1))
                                            if t.tzinfo is None:
                                                t = t.replace(tzinfo=timezone.utc)
                                        except Exception:
                                            t = None
                                        if t and t <= last_ts:
                                            continue
                                error_count += 1
                except Exception:
                    continue
        errors_found = error_count > 0
    except Exception:
        errors_found = False
        error_count = 0

# update last_call file to now
try:
    os.makedirs(os.path.dirname(LAST_CALL_FILE), exist_ok=True)
    with open(LAST_CALL_FILE, 'w') as f:
        json.dump({'last_call': now.isoformat()}, f)
except Exception:
    pass

out = {
    'idle_seconds': idle_seconds,
    'checked_since': checked_since,
    'errors_found': errors_found,
    'error_count': error_count,
    'report_url': REPORT_URL if errors_found else None
}
print(json.dumps(out))
