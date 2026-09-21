FROM python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /app

# Pinned μ-law conversion keeps generated prompt bytes reproducible.
RUN apt-get update && \
    apt-get install --yes --no-install-recommends \
        libsox-fmt-base=14.4.2+git20190427-3.5 \
        sox=14.4.2+git20190427-3.5 && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.12.15

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# The female LJSpeech voice is public-domain training data. Pin both artifacts
# to an immutable piper-voices revision and verify their bytes during the build;
# no model download occurs while rendering deployment-private prompts.
ARG PIPER_VOICE_COMMIT=f5a6e9094787fd865d65cb024472f977f9c542b5
ARG PIPER_VOICE_MODEL_SHA256=6f52a751e2349abe7a76735eb09dc1875298c77ea2342ffd2fef79ff81b87f22
ARG PIPER_VOICE_CONFIG_SHA256=141d612cc0a95ed7efc1ca936b845c2364967f2e9217c5dbfcf69fc4d6c65860
RUN set -eux; \
    voice_directory=/opt/frontporch/piper; \
    voice_name=en_US-ljspeech-medium; \
    voice_base_url="https://huggingface.co/rhasspy/piper-voices/resolve/${PIPER_VOICE_COMMIT}/en/en_US/ljspeech/medium/${voice_name}.onnx"; \
    mkdir -p "${voice_directory}"; \
    python -c 'import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' \
        "${voice_base_url}" "${voice_directory}/${voice_name}.onnx"; \
    python -c 'import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' \
        "${voice_base_url}.json" "${voice_directory}/${voice_name}.onnx.json"; \
    echo "${PIPER_VOICE_MODEL_SHA256}  ${voice_directory}/${voice_name}.onnx" | sha256sum --check --strict; \
    echo "${PIPER_VOICE_CONFIG_SHA256}  ${voice_directory}/${voice_name}.onnx.json" | sha256sum --check --strict

COPY . .

EXPOSE 8000

CMD ["gunicorn", "frontporch.wsgi:application", "--bind", "0.0.0.0:8000"]
