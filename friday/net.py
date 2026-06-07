"""轻量网络工具（避免从 server 模块导入）。"""

from __future__ import annotations

import socket


def find_free_port(start: int = 8765, *, attempts: int = 50) -> int:
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise OSError(f"无法在 127.0.0.1:{start}-{start + attempts - 1} 找到空闲端口")
