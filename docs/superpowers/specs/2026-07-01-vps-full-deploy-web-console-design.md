# VPS Full Deployment And Web Console Design

## Context

The project already contains a FastAPI backend, Telegram polling bot, Celery tasks,
PostgreSQL, Redis, MLflow, a Next.js frontend, Dockerfiles, Docker Compose, and
Nginx config. The user has selected a 4H4G Ubuntu 22.04 x64 server and chose the
full deployment option.

## Confirmed Direction

Use the full deployment profile:

- Nginx reverse proxy on port 80.
- Next.js frontend built and served in production mode.
- FastAPI backend served without development reload.
- Telegram bot running as a long-polling service.
- PostgreSQL for persistent application data.
- Redis for cache and Celery broker.
- Celery Worker and Celery Beat enabled.
- MLflow enabled for experiment tracking.

The frontend will initially follow the approved console mockup. UI can be refined
later without changing the backend deployment contract.

## Architecture

The server will run Docker Compose on Ubuntu 22.04. Containers communicate on the
internal Compose network. Public access goes through Nginx:

- `/` routes to the Next.js frontend.
- `/v1/` routes to FastAPI.
- `/docs`, `/openapi.json`, and `/health` route to FastAPI.
- MLflow can be exposed on port `5000` or placed behind Nginx later.

The production Compose setup must avoid development-only behavior:

- Backend command uses `uvicorn main:app --host 0.0.0.0 --port 8000`.
- Frontend command uses `pnpm start` after `pnpm build`.
- Source-code bind mounts are removed from production services.
- Persistent volumes are used for PostgreSQL and MLflow artifacts.

## Frontend Scope

Build a dashboard-first operational web app, not a marketing landing page.

Initial pages:

- Dashboard: service status, today count, analyzed count, value candidate count,
  recent performance, recent predictions, and top value outputs.
- Today: table of current-day matches with analyzed/review status.
- Single prediction: form that submits home/away or free-text match query to
  `/v1/predict` and renders engine output.
- Match detail: show latest report, value candidates, EV/Kelly/edge, odds
  snapshots, and settlement status.
- Stats: performance buckets and review recommendations.
- System: lightweight backend health and deployment status view.

The visual style should stay dense, restrained, and scan-friendly. It should use
stable table layouts, compact cards, clear statuses, and professional spacing.

## Data Flow

Frontend data comes from existing FastAPI endpoints where possible:

- `/health`
- `/v1/stats`
- `/v1/stats/performance`
- `/v1/predictions/recent`
- `/v1/matches/today`
- `/v1/matches/{fixture_id}`
- `/v1/predict`

If a UI panel needs data that is not available yet, add a small focused API
endpoint rather than hard-coding frontend-only mock data.

Prediction flow:

1. User enters a match in the web app or Telegram.
2. Backend `PredictionService` resolves the fixture through API-Football.
3. The engine orchestrator runs the unified prediction pipeline.
4. Prediction, value candidates, odds snapshots, and report text are persisted.
5. Web UI reads the persisted output and presents it in dashboard/detail views.

## Error Handling

Frontend should render useful empty and degraded states:

- API unavailable: show offline status and preserve the page layout.
- No matches or predictions: show an empty table state.
- Ambiguous match query: show backend candidate/clarification message.
- Prediction failure: show backend error message without breaking navigation.

Server deployment should include restart policies and health checks for the core
services. Secrets must stay in `.env` on the server and must not be committed.

## Testing And Verification

Before pushing:

- Run Python Ruff checks.
- Run Python compile check.
- Run existing backend tests.
- Run frontend lint/build.

After deployment:

- Verify `docker compose ps`.
- Verify `http://SERVER_IP/health`.
- Verify `http://SERVER_IP/`.
- Verify `http://SERVER_IP/docs`.
- Verify Telegram polling logs.
- Verify MLflow is reachable if exposed.
- Run one web prediction request and confirm it appears in recent predictions.

## Deployment Notes

The user will provide server IP, username, and password after the design is
accepted. The password must only be used for SSH deployment and must not be
printed in summaries or committed to files.

If no domain is available, deploy by IP first. HTTPS and domain-based routing can
be added later with DNS and Certbot.
