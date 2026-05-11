# Kimi2API Admin Dashboard

This directory contains the React/Vite frontend for the `/admin` dashboard.

## Commands

```bash
npm ci
npm run dev
npm run build
npm run lint
```

`npm run build` writes production assets to `../app/static/dist`.

## Local Development

Run the FastAPI backend on port `8003`:

```bash
PORT=8003 uv run python run.py
```

Then start Vite from this directory:

```bash
npm run dev
```

`vite.config.ts` proxies `/admin/api`, `/v1`, and `/healthz` to `http://localhost:8003`.

## Production Serving

The backend serves built dashboard assets from `/admin` and `/assets`.
