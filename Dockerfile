# syntax=docker/dockerfile:1.7

FROM node:22-bookworm-slim AS frontend-builder

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund

COPY frontend/index.html \
     frontend/tsconfig.json \
     frontend/tsconfig.app.json \
     frontend/tsconfig.node.json \
     frontend/vite.config.ts ./
COPY frontend/src ./src

RUN npm run build


FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# Зависимости находятся в отдельном слое и не переустанавливаются при каждом
# изменении исходников.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY alembic.ini ./
COPY migrations ./migrations
COPY megamarket ./megamarket
COPY main.py set_seller_links.py ./
COPY --from=frontend-builder /build/frontend/dist ./frontend/dist

RUN groupadd --system app && \
    useradd --system --gid app --create-home app && \
    mkdir -p /app/output /var/lib/megamarket/jobs && \
    chown -R app:app /app/output /var/lib/megamarket/jobs

USER app

EXPOSE 8000 8001

# По умолчанию образ запускает локальный API с пользовательским интерфейсом.
CMD ["uvicorn", "megamarket.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
