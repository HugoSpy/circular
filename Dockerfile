# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim@sha256:4b150b48b4116e2a22f2c39cc27025fbf4f153e2078fd3b14d159fdb5c7279da AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/build_ca; fi; \
    npm ci --ignore-scripts
COPY index.html tsconfig.json vite.config.ts ./
COPY src ./src
RUN npm run build

FROM python:3.12-alpine3.24@sha256:5789aa194f757888f41fa3d48e14b6feaa1b57c0af0b56fcb1372d6474d3bff0 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    CIRCULAR_HOST=0.0.0.0 CIRCULAR_PORT=4310 CIRCULAR_ENV=production
WORKDIR /app
COPY requirements.lock ./
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi; \
    pip install --no-cache-dir --require-hashes -r requirements.lock \
    && addgroup -g 10001 circular \
    && adduser -D -H -u 10001 -G circular circular
COPY --chown=circular:circular backend ./backend
COPY --chown=circular:circular LICENSE THIRD_PARTY_NOTICES.md ./
COPY --from=frontend --chown=circular:circular /build/dist ./dist
USER 10001:10001
EXPOSE 4310
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:4310/api/ready', timeout=3)" || exit 1
CMD ["python", "-m", "backend"]
