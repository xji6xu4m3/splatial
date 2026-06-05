# Splatial — One-Command Phone Onboarding (Docker) Design

**Date:** 2026-06-05
**Status:** Approved (brainstorming) → ready for implementation plan
**Goal:** Let a non-developer ("HR") run the whole capture → reconstruct → view pipeline on any NVIDIA-GPU machine with **one command**, and reach it from a phone via a printed URL/QR — **two steps after a one-time host setup.**

## Problem

Today a demo requires a technical operator to:
1. Start the Flask upload server (`tools/upload_server.py`) in the correct **conda** env (`anysplat`) — with a known venv/conda leak foot-gun.
2. Start the Vite viewer dev server (`web`, `:5173`) separately.
3. Ensure the phone shares the laptop's Wi-Fi, find the host IP, and hand over the URL.

Two servers, two ports, an env that can silently break, cross-origin CORS between them, and manual IP discovery. There is no single launcher.

## Solution (Approach A: single container, single port, one URL)

A portable Docker image, published prebuilt to a public registry, that folds **everything** into one process on one port, adapts to the host GPU, and prints the phone URL + QR on startup.

### Decisions (from brainstorming)
- **Target:** any Linux machine with an NVIDIA GPU + driver (portable image). NVIDIA-only.
- **Delivery:** prebuilt image pulled from **GHCR (public)** — no repo clone, no build, no login for HR.
- **Weights:** never in git. Pulled from HuggingFace (`lhjiang/anysplat`, MIT) at **image build** and baked into the HF cache; runtime is offline (`HF_HUB_OFFLINE=1`).
- **One port, one URL** for capture + viewer + scene files (no CORS).

## 1. Architecture — unified server

The container runs **one** server (`serve.py`, an evolution of `tools/upload_server.py`) owning every route:

| Route | Serves |
|---|---|
| `GET /` | Capture page (upload form + "your scenes" gallery) |
| `POST /upload` | Accept video → spawn background reconstruct → progress page |
| `GET /status/<scene>` | Reconstruction progress (poll) |
| `GET /view?scene=<id>` | The **built** Three.js viewer (static SPA) — replaces the `:5173` Vite server |
| `GET /scenes/<id>/*` | `scene.ply` / `scene.json` (same origin → no CORS) |
| `GET /assets/*` | Viewer JS/CSS build |
| `GET /healthz` | Liveness for Docker `HEALTHCHECK` |

**Two structural wins:**
1. **No conda, no venv leak.** The image's base Python **is** the AnySplat environment (CUDA torch + AnySplat installed at build). The reconstruct worker calls `modules.reconstruct.cli` directly — the `conda run` shell-out and the venv/conda leak bug disappear.
2. **No cross-origin dance.** Capture page, viewer, and scene files share one origin; the current `:5173 ↔ :8090` CORS handling for the up-vector save is removed.

**Repo change:** viewer gains a production `vite build` (output `web/dist/`); `serve.py` mounts that build + the `scenes/` dir as static. The reconstruction pipeline, data contracts, and viewer logic are **unchanged** — packaging/serving refactor only.

## 2. Docker image, weights, GPU portability, publish

**One image across NVIDIA cards.** Image bundles the CUDA **runtime** (12.1); the host supplies the driver via nvidia-container-toolkit. CUDA is forward-compatible, so the same image runs on 3090 / 4070 Ti / A100 / L4 / H100 — any host whose driver meets the floor (CUDA 12.1 → driver ≥ 525). `torch`, `xformers`, `spconv` are baked as multi-arch wheels (Ampere/Ada/Hopper); HR compiles nothing.

**Adapts to the GPU (VRAM auto-detection at startup):** read `torch.cuda.get_device_properties(0).total_memory` and choose the default view cap:

| Detected VRAM | Default `MAX_VIEWS` |
|---|---|
| ≤ 12 GB | 16 |
| 16–24 GB | 32 |
| ≥ 40 GB | 48 |

Overridable via `-e MAX_VIEWS=…`; the existing OOM-recovery ladder (16→12→10→8) stays as the safety net. Bigger GPU → denser scan automatically (the "view count is the lever" finding).

**Image build (multi-stage):**
- **Stage 1 (node):** `vite build` the viewer → `web/dist/`.
- **Stage 2 (cuda):** base `pytorch/pytorch:2.2.0-cuda12.1-cudnn8-runtime`; `pip install -e .` + AnySplat deps; copy `web/dist`; `huggingface_hub.snapshot_download('lhjiang/anysplat')` into the baked HF cache.

**Publish:** GitHub Actions builds + pushes to **GHCR** on a release tag, as a **public** package.

**Portability caveats (documented):**
- Host driver must meet the CUDA 12.1 floor (≥ 525); older fails with a clear message.
- Brand-new arch (e.g. Blackwell/sm_100) may need a torch bump; covered: 30xx/40xx/A100/L4/H100.
- NVIDIA only — no AMD/ROCm or Apple-Silicon path.

## 3. Networking & the phone experience

**LAN reachability via `--network host`** (Linux host): server binds `0.0.0.0:8080` on the host LAN, and IP detection is trivial. On startup it prints a banner:

```
┌─────────────────────────────────────────┐
│  Splatial is live. On your phone open:   │
│      http://<host-lan-ip>:8080           │
│  [ ASCII QR code of that URL ]           │
│  (phone must share this Wi-Fi)           │
└─────────────────────────────────────────┘
```

QR rendered to the terminal with the `qrcode` lib.

**No HTTPS headache.** The capture page uses **file upload** (record in the phone's native Camera app → pick the file), not in-browser `getUserMedia` — so it works over plain HTTP on a LAN IP (no secure-context requirement). Native-camera capture is also the best-quality path per the README A/B.

**Persistence:** scenes are ephemeral in-container, so the run command mounts a host volume.

**The HR-facing flow:**
> **One-time host setup** (documented, copy-paste): install Docker + NVIDIA driver + nvidia-container-toolkit.
> **Step 1:** `docker run --gpus all --network host -v $PWD/scenes:/app/scenes ghcr.io/xji6xu4m3/splatial`
> **Step 2:** scan the QR (or open the printed URL) on your phone, same Wi-Fi → record a room → reconstructs (~1–2 min) → tap to view in 3D.

`--network host` LAN exposure assumes a Linux host (the NVIDIA target); Docker Desktop (Mac/Windows) isn't a CUDA host anyway, consistent with scope.

## 4. Error handling & testing

**Error handling — every failure yields a next step, never a stack trace:**

| Failure | Detection → message |
|---|---|
| No `--gpus` / no GPU | `torch.cuda.is_available()` false → "No CUDA GPU visible. Re-run with `--gpus all` + nvidia-container-toolkit." |
| Driver too old | CUDA init throws → "NVIDIA driver too old — need ≥ 525 for CUDA 12.1." |
| Port in use | bind error → "Port 8080 busy — set `-e PORT=…` or stop the other process." |
| Bad/oversized video | existing extension + size guard → inline error on capture page |
| Reconstruction fails (OOM after ladder, or model error) | status `error:<msg>` → phone progress page shows it + hint (shorter clip / fewer views) |

`GET /healthz` backs a Docker `HEALTHCHECK`.

**Testing — three tiers, most GPU-free:**
1. **Pure logic (TDD, CI):** VRAM→`MAX_VIEWS` table; LAN-IP detection + URL/QR formatting; existing `capture` + `scene_store` tests.
2. **Server routes (CI, reconstructor mocked):** `GET /` capture page, `GET /view` serves viewer build, `GET /scenes/<id>/scene.json` same-origin, `POST /upload` enqueues, `/healthz` ok.
3. **GPU end-to-end (manual / GPU runner — acceptance test):** canned short clip → `/upload` → poll `/status` → assert `scene.ply` + `scene.json`; Playwright on `/view?scene=<id>` verifying **draw calls + screenshot** (verify splats *draw*, not FPS). Container build smoke (build → boot → curl `/healthz` `/` `/view`) runs GPU-free.

## Build surface (each a focused unit)
- `serve.py` — routes + static mounts + recon worker + startup banner + `/healthz` + VRAM-autoscale hook.
- VRAM-autoscale helper (pure function).
- `Dockerfile` (multi-stage) + `.dockerignore`.
- Viewer `vite build` → `web/dist` (build config).
- `.github/workflows/docker-publish.yml` — GHCR publish on release tag.
- README "Run on your phone (Docker)" section — one-time prereqs + the two steps.
- Tests: autoscale + IP/QR (unit), server routes (CI mocked), container smoke (CI), GPU e2e (manual).

## Out of scope
- Object placement / voice→GLB / scene editing (separate roadmap).
- Non-NVIDIA GPUs; cloud-hosted always-on deployment; in-browser camera capture.
- Reconstruction algorithm changes (this is packaging/serving only).

## Success criteria
- On a fresh NVIDIA-GPU Linux host with the one-time toolkit installed, a non-developer runs the single `docker run` line, sees a URL + QR, scans it on a phone (same Wi-Fi), records a room, and views the reconstructed 3D scene — with **no conda, no Vite, no manual IP lookup, no code**.
- The same image, unchanged, runs on a different-VRAM NVIDIA GPU and auto-scales the view cap.
