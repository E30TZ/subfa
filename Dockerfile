FROM python:3.12-slim

# ffmpeg is required for audio extraction and subtitle burn-in.
# fonts-vazirmatn gives proper Persian subtitle rendering; if the
# package is unavailable in the mirror, the build still succeeds and
# libass falls back to a system font.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && (apt-get install -y --no-install-recommends fonts-vazirmatn \
        || echo "Vazirmatn package unavailable, using system font fallback") \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY subfa ./subfa
COPY bot ./bot
COPY web ./web
COPY glossaries ./glossaries
RUN pip install --no-cache-dir ".[bot,web,translate,persian]"

# Models live in one cache folder inside the image.
ENV SUBFA_MODEL_CACHE=/app/models
# Set BUNDLE_MODELS=1 at build time to download every ASR model
# into the image, so the container runs with zero runtime downloads
# (the image grows by roughly 5 GB):
#   docker build --build-arg BUNDLE_MODELS=1 .
# The build machine needs network access (or HF_ENDPOINT set to a
# reachable mirror) for that one build.
ARG BUNDLE_MODELS=0
RUN if [ "$BUNDLE_MODELS" = "1" ]; then subfa download-models; fi

EXPOSE 8000
CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000"]
