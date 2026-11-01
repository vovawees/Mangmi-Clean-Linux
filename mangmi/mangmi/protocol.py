# SPDX-License-Identifier: GPL-2.0-or-later
"""mangmi-hwd control socket: one JSON object per line, both directions."""
from __future__ import annotations

import json
import os
import socket

SOCKET = os.environ.get("MANGMI_HWD_SOCKET", "/run/mangmi/hwd.sock")


class DaemonUnavailable(RuntimeError):
    pass


def request(msg: dict, timeout: float = 5.0) -> dict:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(SOCKET)
            s.sendall((json.dumps(msg) + "\n").encode())
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
    except (FileNotFoundError, ConnectionRefusedError, PermissionError) as e:
        raise DaemonUnavailable(f"mangmi-hwd is not reachable at {SOCKET}: {e}") from e
    if not buf:
        raise DaemonUnavailable("empty reply from mangmi-hwd")
    return json.loads(buf)
