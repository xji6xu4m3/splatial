"""Host-network helpers: find the LAN IP and render the startup banner + QR.

The phone reaches the container at the host's LAN IP (we run with --network host), so we
detect it via a UDP socket to a public address (no packets actually sent) and fall back to
loopback if there's no network.
"""
import socket

import qrcode


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))   # no traffic; just selects the outbound interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        try:
            s.close()
        except OSError:
            pass


def viewer_url(ip: str, port: int) -> str:
    return f"http://{ip}:{port}"


def qr_ascii(text: str) -> str:
    qr = qrcode.QRCode(border=1)
    qr.add_data(text)
    qr.make(fit=True)
    rows = qr.get_matrix()
    return "\n".join("".join("██" if cell else "  " for cell in row) for row in rows)


def startup_banner(port: int) -> str:
    url = viewer_url(lan_ip(), port)
    return (
        "\n" + "=" * 48 + "\n"
        "  Splatial is live. On your phone, open:\n"
        f"      {url}\n"
        "  (the phone must share this Wi-Fi)\n\n"
        f"{qr_ascii(url)}\n"
        + "=" * 48 + "\n"
    )
