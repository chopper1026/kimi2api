FROM python:3.12-slim AS base

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app/ app/
COPY run.py .

RUN mkdir -p /app/data

ENV HOST=0.0.0.0
ENV PORT=8000
ENV TIMEZONE=Asia/Shanghai
ENV TZ=Asia/Shanghai

EXPOSE 8000

CMD ["uv", "run", "python", "run.py"]
