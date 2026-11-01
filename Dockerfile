# syntax=docker/dockerfile:1

# Package index. Default is an Iranian PyPI mirror because files.pythonhosted.org
# is filtered in Iran (REPORT #012). CI overrides it with the official PyPI.
ARG PIP_INDEX_URL=https://repo.hmirror.ir/python/simple

# ---------- 1. CSS: compile Tailwind (Node is build-time only) ----------
FROM node:22-alpine AS css
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend ./frontend
COPY templates ./templates
COPY apps ./apps
RUN npm run build:css

# ---------- 2. Base: Python + dependencies ----------
FROM python:3.12-slim AS base
ARG PIP_INDEX_URL
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    UV_INDEX_URL=${PIP_INDEX_URL} \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -i "${PIP_INDEX_URL}" uv==0.13.5 \
 && uv venv /opt/venv
WORKDIR /app

# ---------- 3. Dev: + test/lint tools; source is bind-mounted by compose ----------
FROM base AS dev
COPY requirements/dev.txt /tmp/requirements.txt
RUN uv pip sync --require-hashes /tmp/requirements.txt

# ---------- 4. Prod: app code + built CSS + collected static, non-root ----------
FROM base AS prod
COPY requirements/base.txt /tmp/requirements.txt
RUN uv pip sync --require-hashes /tmp/requirements.txt
COPY . .
COPY --from=css /build/static/css ./static/css
RUN SECRET_KEY=build-only DATABASE_URL=sqlite:////tmp/build.db ALLOWED_HOSTS=localhost \
    PAYMENT_GATEWAY_ORDER=zarinpal \
    DJANGO_SETTINGS_MODULE=config.settings.prod python manage.py collectstatic --noinput \
 && useradd --system --uid 1000 --home /app app \
 && mkdir -p /app/media /app/private && chown -R app:app /app/media /app/private
USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-", "--no-control-socket"]
