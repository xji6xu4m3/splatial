"""`python -m modules.serve` — detect the GPU's VRAM to set the default view cap, print the
phone URL + QR, then serve. Run with --network host so the LAN IP is reachable from a phone.
"""
import os

from modules.serve.app import create_app
from modules.serve.gpu import default_max_views
from modules.serve.net import find_free_port, startup_banner


def _detect_total_vram() -> int | None:
    try:
        import torch
        if not torch.cuda.is_available():
            print("WARNING: no CUDA GPU visible — run with `--gpus all` and "
                  "nvidia-container-toolkit. Reconstruction will fail until then.")
            return None
        return torch.cuda.get_device_properties(0).total_memory
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: could not query GPU ({e}); defaulting view cap to 16.")
        return None


def main() -> None:
    if "MAX_VIEWS" not in os.environ:
        cap = default_max_views(_detect_total_vram())
        os.environ["MAX_VIEWS"] = str(cap)
        print(f"GPU view cap (MAX_VIEWS) auto-set to {cap}")
    # Always pin MIN_VIEWS to MAX_VIEWS (auto-set OR operator-supplied) so the reconstruct CLI
    # never sees min_views > max_views — e.g. a `-e MAX_VIEWS=8` override must not leave
    # MIN_VIEWS at the CLI's hard-coded 16.
    os.environ.setdefault("MIN_VIEWS", os.environ["MAX_VIEWS"])

    requested = int(os.environ.get("PORT", "8080"))
    try:
        port = find_free_port(requested)
    except OSError:
        raise SystemExit(
            f"ERROR: port {requested} (and the next few) are all in use. Free it "
            f"(`lsof -i :{requested}` then stop that process) or set a different PORT."
        )
    if port != requested:
        print(f"Port {requested} is in use — serving on {port} instead "
              f"(the URL/QR below already reflect it).")

    print(startup_banner(port))
    app = create_app()
    app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    main()
