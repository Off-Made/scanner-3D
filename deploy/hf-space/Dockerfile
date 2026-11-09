# Backend Scan3D per un Hugging Face Space (SDK "docker", CPU basic gratuito: 2 vCPU / 16 GB).
# L'immagine viene costruita sui server di Hugging Face: NON serve Docker sul tuo PC.
# NOTA: questo Dockerfile non è stato costruito in locale (niente Docker): il primo build avviene sullo Space.
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-venv python3-pip colmap curl unzip ca-certificates libgl1 libglib2.0-0 libgomp1 libusb-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# OpenMVS: binari precompilati ufficiali per Ubuntu
ARG OPENMVS_VERSION=v2.4.0
RUN mkdir -p /opt/openmvs \
    && curl -fsSL -o /tmp/omvs.zip "https://github.com/cdcseacave/openMVS/releases/download/${OPENMVS_VERSION}/OpenMVS_Ubuntu_x64.zip" \
    && unzip -q /tmp/omvs.zip -d /tmp/omvs \
    && find /tmp/omvs -type f \( -name InterfaceCOLMAP -o -name DensifyPointCloud -o -name "*.so*" \) -exec cp {} /opt/openmvs/ \; \
    && chmod +x /opt/openmvs/InterfaceCOLMAP /opt/openmvs/DensifyPointCloud \
    && rm -rf /tmp/omvs /tmp/omvs.zip

RUN useradd -m -u 1000 user
WORKDIR /home/user/app
COPY --chown=user requirements.txt .
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt
COPY --chown=user server/app ./server/app
USER user

# Su uno Space le richieste arrivano dal proxy interno di Hugging Face (rete privata):
# l'IP reale del client è in X-Forwarded-For. Con 2 vCPU uso 2 thread.
ENV PATH=/opt/venv/bin:$PATH \
    OPENMVS_DIR=/opt/openmvs \
    DATA_DIR=/tmp/scan3d-data \
    TRUSTED_PROXIES=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16 \
    TRUSTED_IP_HEADERS=X-Forwarded-For \
    PHOTO_FEATURE_THREADS=2 \
    PHOTO_MATCH_THREADS=2

EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--app-dir", "server", "--host", "0.0.0.0", "--port", "7860"]
