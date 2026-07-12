# CuraVar API image. Build context is the repo root (…/files (16)) so this can
# install the curavar engine package alongside the web layer.
#
#   docker build -f web/api/Dockerfile -t curavar-api .
#
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 1. Install the tested engine package (its own pyproject; zero runtime deps).
COPY curavar/ /app/curavar/
RUN pip install /app/curavar

# 2. Install the API's web dependencies.
COPY web/api/requirements.txt /app/web/api/requirements.txt
RUN pip install -r /app/web/api/requirements.txt

# 3. Copy the web package (the API imports `web.api.*`).
COPY web/__init__.py /app/web/__init__.py
COPY web/api/ /app/web/api/

EXPOSE 8000

# The Anthropic key, if any, is passed at runtime via the environment and stays
# server-side. With no key, the app runs entirely in offline replay mode.
CMD ["uvicorn", "web.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
