# NurFX.ai Backend

Production-ready Django REST Framework backend for an AI-powered Forex analysis platform.

## Architecture

```
Client (Web/Mobile)
    │
    ▼
Django REST API (Gunicorn)
    ├── authentication/   Google OAuth 2.0 + SimpleJWT
    ├── analysis/         Chart upload, history, status polling
    ├── tokens/           Coupons, subscriptions, transactions
    └── ai_engine/        Celery task → one Claude Opus 5 vision call
            │
            └── ICT/SMC read + risk validation + strict JSON, in one turn.
                Opus 5 may call `zoom_chart_region` first to re-read price
                labels at full resolution before committing to levels.
    │
    ▼
Telegram Bot (Aiogram 3.x) — Admin coupon generation & redemption
```

## Quick Start

### 1. Clone & configure

```bash
cp .env.example .env
# Edit .env with your secrets (never commit .env)
```

### 2. Docker (recommended)

```bash
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

API available at `http://localhost:8000`

### 3. Local development

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Run Celery worker separately:

```bash
celery -A config worker -l info -Q default,ai_pipeline
```

Run Telegram bot:

```bash
python -m apps.bot.runner
```

## API Endpoints

| Method | Endpoint | Description | Rate Limit |
|--------|----------|-------------|------------|
| POST | `/api/v1/auth/google/` | Google OAuth sign-in | 5/min |
| POST | `/api/v1/auth/refresh/` | Refresh JWT | 5/min |
| POST | `/api/v1/auth/logout/` | Blacklist refresh token | — |
| GET | `/api/v1/auth/me/` | User profile | — |
| GET | `/api/v1/auth/balance/` | Token balance | — |
| POST | `/api/v1/analysis/run/` | Submit chart for analysis | 5/min |
| GET | `/api/v1/analysis/history/` | Analysis history | — |
| GET | `/api/v1/analysis/<uuid>/` | Analysis detail/result | — |
| GET | `/api/v1/analysis/<uuid>/image/` | Chart image (owner only) | — |
| POST | `/api/v1/tokens/redeem/` | Redeem coupon code | 10/min |
| GET | `/api/v1/tokens/packages/` | Subscription packages | — |
| GET | `/api/v1/tokens/transactions/` | Transaction history | — |

## Token Economy

| Item | Value |
|------|-------|
| Analysis cost | 3 tokens |
| Base token value | 8,000 UZS |
| Welcome gift | 6 tokens (2 free analyses) |

### Subscription Packages

| Package | Tokens | Analyses | Price (UZS) | Per Token |
|---------|--------|----------|-------------|-----------|
| BASIC | 30 | 10 | 210,000 | 7,000 |
| **PRO** ★ | 90 | 30 | 540,000 | 6,000 |
| VIP MAX | 210 | 70 | 1,197,000 | 5,700 |

## Security Features

- **Input validation:** DRF serializers on all endpoints
- **Image sanitization:** EXIF stripped, re-encoded via Pillow (PNG, capped at 2576px); size (5 MB) *and* pixel-count (25 MP) limits block decompression bombs
- **Rate limiting:** `django-ratelimit` + DRF `ScopedRateThrottle`; admin login capped at 10 POST/min per IP
- **JWT:** Short-lived access tokens (15 min) in HTTP-only secure cookies — `CookieJWTAuthentication` reads the cookie, so browser clients never need the token in JS-reachable storage. `Authorization: Bearer` still works for mobile/API clients.
- **Coupons:** 8-character random suffix (36⁸ ≈ 2.8×10¹² space), single-use, 30-day expiry
- **Chart images:** served only to the owning user via `/analysis/<uuid>/image/` — never from the public media URL
- **CORS:** Whitelisted origins only (no wildcard)
- **SQL injection:** Django ORM parametrized queries exclusively
- **Secrets:** `django-environ` — all keys in `.env`, no insecure defaults in code
- **HTTPS headers:** HSTS, XSS filter, content-type nosniff, frame deny

## AI engine

One `claude-opus-5` request per analysis. Tuning lives in `.env`:

| Variable | Default | Notes |
|----------|---------|-------|
| `AI_CLAUDE_MODEL` | `claude-opus-5` | |
| `AI_CLAUDE_EFFORT` | `high` | `low`–`max`. Sweep against your own results; higher is not automatically better. |
| `AI_CLAUDE_MAX_TOKENS` | `16000` | Covers thinking *and* the answer. |
| `AI_ENABLE_REFUSAL_FALLBACK` | `True` | Re-runs a refused request on a fallback model. Turn off if the beta parameter starts rejecting requests. |

The system prompt is cached (`cache_control: ephemeral`), so repeat analyses pay
~0.1× on the shared prefix.

### Production checklist

- Set a unique `DJANGO_ADMIN_URL` (not `admin/`) so the panel isn't a predictable scan target
- Set `POSTGRES_PASSWORD` and a matching `DATABASE_URL` — startup fails if `DATABASE_URL` is missing
- Postgres and Redis are not published to the host in `docker-compose.yml`; keep it that way
- Do not serve `MEDIA_ROOT/charts/` from nginx — chart screenshots may contain account details

## Telegram Admin Commands

```
/generate_coupon tokens=21 price=168000
/redeem NURFX-8-X92A7K4T
/balance
```

Admin IDs configured via `TELEGRAM_ADMIN_IDS` in `.env`.

## License

Proprietary — NurFX.ai
