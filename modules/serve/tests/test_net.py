import re
import socket

import pytest

from modules.serve import net


def test_find_free_port_returns_preferred_when_free():
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("0.0.0.0", 0))
    free = probe.getsockname()[1]
    probe.close()
    assert net.find_free_port(free) == free


def test_find_free_port_skips_busy():
    busy_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    busy_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    busy_sock.bind(("0.0.0.0", 0))
    busy_sock.listen()
    busy = busy_sock.getsockname()[1]
    try:
        got = net.find_free_port(busy, attempts=8)
        assert got != busy and busy < got <= busy + 7
    finally:
        busy_sock.close()


def test_find_free_port_raises_when_none_free():
    busy_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    busy_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    busy_sock.bind(("0.0.0.0", 0))
    busy_sock.listen()
    busy = busy_sock.getsockname()[1]
    try:
        with pytest.raises(OSError):
            net.find_free_port(busy, attempts=1)  # only the busy port in range
    finally:
        busy_sock.close()


def test_lan_ip_returns_dotted_quad():
    ip = net.lan_ip()
    assert re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip)

def test_lan_ip_falls_back_on_error(monkeypatch):
    class BoomSocket:
        def __init__(self, *a, **k): pass
        def connect(self, *a, **k): raise OSError("no network")
        def getsockname(self): raise AssertionError("unreachable")
        def close(self): pass
    monkeypatch.setattr(net.socket, "socket", BoomSocket)
    assert net.lan_ip() == "127.0.0.1"

def test_viewer_url():
    assert net.viewer_url("192.168.1.5", 8080) == "http://192.168.1.5:8080"

def test_qr_ascii_is_nonempty_multiline():
    art = net.qr_ascii("http://192.168.1.5:8080")
    assert isinstance(art, str) and "\n" in art and len(art) > 50

def test_banner_contains_url(monkeypatch):
    monkeypatch.setattr(net, "lan_ip", lambda: "10.0.0.9")
    text = net.startup_banner(8080)
    assert "http://10.0.0.9:8080" in text
