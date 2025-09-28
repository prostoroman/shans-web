# Shan's Web - Financial Analysis Platform

A production-ready Django 5.x application for financial analysis, portfolio optimization, and market insights.

## Features

- **Market Analysis**: Detailed stock analysis with key metrics, fundamentals, and performance data
- **Portfolio Optimization**: Modern Portfolio Theory implementation with efficient frontier analysis
- **Comparison Tools**: Side-by-side stock comparison with correlation analysis
- **User Management**: Tiered access (Basic/Pro) with saved portfolios and viewing history
- **API Integration**: Financial Modeling Prep (FMP) Premium integration via official Python client
- **Internationalization**: Multi-language support (English/Russian) with gettext
- **SEO Optimized**: Server-side rendering with robots.txt, sitemap.xml, and canonical tags

## Technology Stack

- **Backend**: Django 5.x, Django REST Framework
- **Database**: PostgreSQL (production), SQLite (development)
- **Authentication**: django-allauth
- **Data Source**: Financial Modeling Prep (FMP) via `fmp_python`
- **Frontend**: Bootstrap 5, Chart.js, Font Awesome
- **Deployment**: Render.com with WhiteNoise for static files
- **Code Quality**: pytest, ruff, black, mypy

## Quick Start

### Prerequisites

- Python 3.11+
- pip
- Git

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/shans-web.git
   cd shans-web
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -e .
   ```

4. **Set up environment variables**
   ```bash
   cp env.example .env
   # Edit .env with your API keys and settings
   ```

5. **Run migrations**
   ```bash
   python manage.py migrate
   ```

6. **Create superuser**
   ```bash
   python manage.py createsuperuser
   ```

7. **Load sample data**
   ```bash
   python manage.py load_prices --symbols AAPL,MSFT,GOOGL --days 1825
   ```

8. **Start development server**
   ```bash
   python manage.py runserver
   ```

Visit `http://127.0.0.1:8000` to see the application.

## Environment Variables

Create a `.env` file with the following variables:

```env
# Django Configuration
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_DEBUG=1
ALLOWED_HOSTS=127.0.0.1,localhost

# Database
DATABASE_URL=sqlite:///db.sqlite3

# Financial Modeling Prep API
FMP_API_KEY=your_fmp_api_key_here

# OpenAI API (for LLM features)
OPENAI_API_KEY=your_openai_api_key_here

# Default Risk-Free Rate
DEFAULT_RF=0.03

# CSRF trusted origins
CSRF_TRUSTED_ORIGINS=https://*.onrender.com
```

## Project Structure

```
shans-web/
├── apps/
│   ├── core/           # Home, health check, SEO pages
│   ├── accounts/       # User profiles, dashboard, tiers
│   ├── data/           # FMP client, data services, models
│   ├── markets/        # Stock info, comparison, metrics
│   ├── portfolio/      # Portfolio analysis, MPT, forecasting
│   └── activity/       # Viewing history, saved sets
├── shans_web/          # Django project settings
├── static/             # CSS, JS, images
├── templates/          # Base templates
├── tests/              # Test suite
├── pyproject.toml      # Dependencies and tool configuration
├── render.yaml         # Render.com deployment config
└── Procfile            # Production server configuration
```

## Key URLs

- `/` - Home page
- `/info/<symbol>` - Stock analysis
- `/compare/<symbols>` - Stock comparison
- `/portfolio` - Portfolio analysis form
- `/dashboard` - User dashboard
- `/account/profile` - User profile
- `/history` - Viewing history
- `/saved` - Saved sets
- `/healthz` - Health check
- `/robots.txt` - SEO robots file
- `/sitemap.xml` - SEO sitemap

## API Endpoints

- `GET /api/info?symbol=AAPL` - Get stock data
- `GET /api/compare?symbols=AAPL,MSFT` - Compare stocks
- `POST /api/portfolio/analyze/` - Analyze portfolio

## User Tiers

### Basic Plan
- Up to 3 saved portfolios
- Compare up to 4 symbols
- 30-day history retention
- Basic analysis features

### Pro Plan
- Up to 50 saved portfolios
- Compare up to 10 symbols
- 365-day history retention
- Advanced optimization
- Forecasting tools
- AI commentary
- Export capabilities

## Development

### Running Tests
```bash
pytest
```

### Code Quality
```bash
ruff check .
black --check .
mypy .
```

### Loading Data
```bash
# Load price data for symbols
python manage.py load_prices --symbols AAPL,MSFT,GOOGL --days 1825

# Load with fundamentals
python manage.py load_prices --symbols AAPL,MSFT --fundamentals
```

## Deployment

### Render.com

1. Connect your GitHub repository to Render
2. Create a new Web Service
3. Use the provided `render.yaml` configuration
4. Set environment variables in Render dashboard
5. Deploy!

### Environment Variables for Production

```env
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=your-production-secret-key
FMP_API_KEY=your_fmp_api_key
OPENAI_API_KEY=your_openai_api_key
DATABASE_URL=postgresql://user:pass@host:port/dbname
CSRF_TRUSTED_ORIGINS=https://your-domain.onrender.com
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Run code quality checks
6. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support, email support@shans-web.com or create an issue on GitHub.

## Roadmap

- [ ] Real-time data streaming
- [ ] Advanced charting with Plotly
- [ ] Mobile app
- [ ] Social features
- [ ] Advanced AI insights
- [ ] Cryptocurrency support
- [ ] Options analysis
- [ ] Backtesting tools