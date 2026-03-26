#!/usr/bin/env python3
"""
auto_append_error_notice.py

Helper used by the assistant to decide whether to append the error-report notice
when replying after an idle period.

Usage: import this module and call get_notice(). Returns None or a tuple
(title, url, count).
"""
import json
import subprocess
import shlex
from pathlib import Path

CHECK_SCRIPT = Path(__file__).resolve().parent.parent / 'scripts' / 'check_reconnect_errors.py'


def get_notice():
    """Run check_reconnect_errors.py and return a dict with notice info if errors found.
    Returns: None if no notice, else dict { 'error_count': int, 'report_url': str }
    """
    if not CHECK_SCRIPT.exists():
        return None
    try:
        p = subprocess.run([str(CHECK_SCRIPT)], capture_output=True, text=True, timeout=30)
        if p.returncode != 0:
            return None
        data = json.loads(p.stdout)
        if data.get('errors_found'):
            return { 'error_count': data.get('error_count', 0), 'report_url': data.get('report_url') }
    except Exception:
        return None
    return None


if __name__ == '__main__':
    n = get_notice()
    if n:
        print(f"NOTICE: {n['error_count']} errors found. See: {n['report_url']}")
    else:
        print('NO_NOTICE')
