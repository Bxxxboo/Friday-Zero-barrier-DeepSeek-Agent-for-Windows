from __future__ import annotations

import socket

import pytest

from friday.instance_lock import try_acquire_instance_lock


@pytest.fixture
def isolated_lock_port(monkeypatch: pytest.MonkeyPatch) -> int:
    """为测试分配临时端口，避免与运行中的星期五实例（58765）冲突。"""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    monkeypatch.setattr("friday.instance_lock._instance_port", lambda: port)
    return port


def test_try_acquire_instance_lock_success(isolated_lock_port: int):
    sock = try_acquire_instance_lock()
    assert sock is not None
    assert sock.getsockname()[1] == isolated_lock_port
    sock.close()


def test_try_acquire_instance_lock_conflict(isolated_lock_port: int):
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        try:
            holder.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        except OSError:
            pass
    holder.bind(("127.0.0.1", isolated_lock_port))
    holder.listen(1)
    try:
        assert try_acquire_instance_lock() is None
    finally:
        holder.close()

    retry = try_acquire_instance_lock()
    assert retry is not None
    retry.close()


def test_dev_and_prod_instance_ports_can_coexist(monkeypatch):
    """测试版与正式版应使用不同单实例端口，可同时 bind。"""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    base = probe.getsockname()[1]
    probe.close()

    monkeypatch.delenv("FRIDAY_DEV", raising=False)
    monkeypatch.setattr("friday.instance_lock._instance_port", lambda: base)
    prod_sock = try_acquire_instance_lock()
    assert prod_sock is not None

    monkeypatch.setenv("FRIDAY_DEV", "1")
    monkeypatch.setattr("friday.instance_lock._instance_port", lambda: base + 1)
    dev_sock = try_acquire_instance_lock()
    assert dev_sock is not None
    assert dev_sock.getsockname()[1] == base + 1

    prod_sock.close()
    dev_sock.close()


def test_edition_ports_differ_for_dev(monkeypatch):
    monkeypatch.delenv("FRIDAY_DEV", raising=False)
    from friday.edition import instance_port

    assert instance_port() == 58765
    monkeypatch.setenv("FRIDAY_DEV", "1")
    assert instance_port() == 58766


def test_focus_existing_window_noop_on_non_windows():
    from unittest.mock import patch

    with patch("friday.instance_lock.sys.platform", "linux"):
        from friday.instance_lock import focus_existing_window

        assert focus_existing_window() is False
