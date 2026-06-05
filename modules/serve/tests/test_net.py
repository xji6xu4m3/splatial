import re
from modules.serve import net

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
