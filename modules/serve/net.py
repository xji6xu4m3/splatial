"""Host-network helpers: find the LAN IP and render the startup banner + QR.

The phone reaches the container at the host's LAN IP (we run with --network host), so we
detect it via a UDP socket to a public address (no packets actually sent) and fall back to
loopback if there's no network.
"""
import errno
import socket

import qrcode


def find_free_port(preferred: int, attempts: int = 11) -> int:
    """Return `preferred` if it can be bound, else the next free port in
    [preferred, preferred+attempts). Raises OSError if none are free.

    Lets the server fall back gracefully when the default port is already taken,
    instead of dying with a raw "Address already in use" traceback."""
    last = None
    for port in range(preferred, preferred + attempts):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # match the dev server's bind
        try:
            s.bind(("0.0.0.0", port))
            return port
        except OSError as e:
            last = e
            if e.errno not in (errno.EADDRINUSE, errno.EACCES):
                raise
        finally:
            s.close()
    raise OSError(f"no free port in {preferred}-{preferred + attempts - 1}") from last


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
