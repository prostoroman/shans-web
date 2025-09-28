shans-web

Server-rendered Django 5 app with DRF API for markets/portfolio analytics. SEO-first SSR, tiered access, and FMP integration.

Features
- Django templates (SSR) + DRF API
- Accounts via django-allauth; tiered plans: basic/pro
- Data ingestion from Financial Modeling Prep (FMP)
- Markets pages: `/info/<symbol>`, `/compare/<symbols>`
- Portfolio analysis: mean-variance, frontier, tangency
- Activity: viewing history, saved sets/portfolios
- i18n ready (default `en`)

Requirements
- Python 3.11+
- SQLite (dev) / Postgres (prod)

Getting started (local)
```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .[dev]
cp .env.example .env
# edit .env as needed
python -m django --version  # sanity check

# Initialize project DB
python manage.py migrate
python manage.py createsuperuser

# Run server
python manage.py runserver
```

Visit `http://localhost:8000`.

Environment
- `DJANGO_SECRET_KEY` (required in prod)
- `DJANGO_DEBUG` (0/1)
- `DATABASE_URL` (Render/Prod)
- `FMP_API_KEY` (for data)
- `DEFAULT_RF` (risk-free, default 0.03)
- `ALLOWED_HOSTS`, `SITE_DOMAIN`

Render deployment
- Render config in `render.yaml`
- Procfile uses gunicorn
- WhiteNoise serves static files

Management commands
```bash
python manage.py load_prices --symbols AAPL,MSFT --days 1825
python manage.py collectstatic --noinput
```

Tests
```bash
pytest -q
```

License
MIT

