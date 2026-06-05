# syntax=docker/dockerfile:1

# ---- Stage 1: build the Three.js viewer (base '/view/') ----
FROM node:20-slim AS viewer
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build          # -> /web/dist

# ---- Stage 2: CUDA runtime image (devel base: nvcc needed to build torch_scatter/pytorch3d) ----
FROM pytorch/pytorch:2.2.0-cuda12.1-cudnn8-devel
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PORT=8080
# Cover Ampere/Ada/Hopper so the compiled CUDA ops run on any of these GPUs.
ENV TORCH_CUDA_ARCH_LIST="8.0;8.6;8.9;9.0"
RUN apt-get update && apt-get install -y --no-install-recommends \
      git build-essential ninja-build ffmpeg libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# AnySplat source: the repo's external_AnySplat/ is gitignored, so clone it at a pinned commit
# (the model code our server imports as `src.model.*`). Delete the unused CC-BY-NC preprocessor —
# we use the MIT-clean modules/reconstruct/preprocess.py instead; the model path never imports it.
RUN git clone --filter=blob:none --no-checkout https://github.com/InternRobotics/AnySplat.git external_AnySplat \
 && git -C external_AnySplat checkout -q 5f5e208a7dd57d52e43ea0d553a95eab526e8775 \
 && rm -f external_AnySplat/src/utils/image.py

# Pin the deps to the combo proven in the dev env: numpy 1.26.4 (the upstream ==1.25.0 conflicts
# with our pyproject >=1.26), pytorch3d at tag V0.7.8. xformers==0.0.24 already requires
# torch==2.2.0 — exactly the base image — so torch is never downgraded.
RUN sed -i 's/numpy==1.25.0/numpy==1.26.4/' external_AnySplat/requirements.txt \
 && sed -i 's#git+https://github.com/facebookresearch/pytorch3d.git#&@V0.7.8#' external_AnySplat/requirements.txt
RUN pip install --no-cache-dir -r external_AnySplat/requirements.txt
RUN pip install --no-cache-dir "flask>=3.0" "qrcode>=7.4"

# App code + the built viewer.
COPY . .
COPY --from=viewer /web/dist /app/web/dist
RUN pip install --no-cache-dir -e .

# Bake the AnySplat weights into the HF cache (build needs network; runtime does not).
RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('lhjiang/anysplat')"
ENV HF_HUB_OFFLINE=1

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
  CMD python -c "import urllib.request,os,sys; p=os.environ.get('PORT','8080'); sys.exit(0 if urllib.request.urlopen('http://localhost:'+p+'/healthz').status==200 else 1)"
CMD ["python", "-m", "modules.serve"]
