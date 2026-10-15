FROM mcr.microsoft.com/dotnet/runtime:8.0-bookworm-slim AS dotnet
FROM python:3.12-slim-bookworm
COPY --from=dotnet /usr/share/dotnet /usr/share/dotnet
ENV PATH="/usr/share/dotnet:${PATH}" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends curl unzip libicu72 libssl3 ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN curl -fL --retry 3 https://github.com/Norbyte/lslib/releases/download/v1.20.4/ExportTool-v1.20.4.zip -o /tmp/lslib.zip \
    && echo '5e02368fb8acafda9b45acba37a3f3bf507fc3d65a083a159abbeab06337190e  /tmp/lslib.zip' | sha256sum -c - \
    && mkdir /opt/lslib && unzip -q /tmp/lslib.zip -d /opt/lslib && rm /tmp/lslib.zip
COPY backend backend
COPY scripts scripts
COPY templates templates
COPY data/equipment_catalog.json data/equipment_catalog.json
COPY data/equipment_presentation.json data/equipment_presentation.json
COPY prompts prompts
COPY web web
ENV MOD_PACKAGER=/opt/lslib/Packed/Tools/Divine.dll
# Build fails unless Linux performs a real PAK round trip. The AI is a labelled fixture.
RUN python -m scripts.verify_delivery --root /tmp/delivery-build-check && rm -rf /tmp/delivery-build-check
ENV MOD_DATA_DIR=/var/data/mod-superman MOD_PUBLIC=1
CMD ["sh", "-c", "exec uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
