# Risk-Free Rate Support Implementation

## Overview

This implementation adds comprehensive risk-free rate support for multiple currencies using the FMP Treasury Rates API. The system now calculates Sharpe ratios using currency-specific risk-free rates instead of a fixed 3% assumption, making the calculations more accurate and realistic.

## Key Features

### 1. Multi-Currency Support
- **32+ supported currencies** including USD, EUR, GBP, JPY, CHF, and many others
- **Currency-specific risk-free rates** with realistic default values
- **Automatic currency detection** from asset data

### 2. FMP Treasury Rates API Integration
- **Real-time treasury data** from FMP API v4 treasury endpoint
- **Robust fallback system** to default rates when API data is unavailable
- **Caching system** with 24-hour TTL for performance
- **Retry logic** with exponential backoff for reliability

### 3. Period-Specific Risk-Free Rates
- **YTD periods**: Uses mid-year risk-free rates for consistency
- **Other periods**: Uses risk-free rates from the middle of the period
- **Date-specific rates**: Can fetch rates for specific dates
- **Period averaging**: Supports averaging rates over time periods

### 4. Enhanced Sharpe Ratio Calculations
- **Currency-aware calculations**: Automatically uses the correct risk-free rate for each currency
- **Proper annualization**: Correctly handles different data frequencies (daily, weekly, monthly)
- **Improved accuracy**: More realistic Sharpe ratios based on actual market conditions

## Implementation Details

### Files Modified/Created

1. **`apps/markets/risk_free_rate_service.py`** (NEW)
   - Main risk-free rate service
   - FMP API integration
   - Multi-currency support
   - Caching and fallback logic

2. **`apps/markets/chart_service.py`** (MODIFIED)
   - Updated `_calculate_metrics` method
   - Added risk-free rate service integration
   - Enhanced logging with currency and risk-free rate information

3. **`apps/markets/metrics.py`** (MODIFIED)
   - Updated `calculate_sharpe_ratio` function
   - Added currency parameter support
   - Enhanced `calculate_metrics` function

4. **`apps/data/fmp_client.py`** (MODIFIED)
   - Enhanced `get_risk_free_yield` function
   - Added 1-year tenor support

### API Integration

The system uses the FMP Treasury Rates API endpoint:
```
https://financialmodelingprep.com/api/v4/treasury
```

**Parameters:**
- `apikey`: FMP API key
- `from`: Start date (YYYY-MM-DD)
- `to`: End date (YYYY-MM-DD)

**Response handling:**
- Extracts yield values from treasury data
- Tries multiple maturity fields (1-year, 3-month, 6-month, 2-year)
- Falls back to default rates if no valid data found

### Default Risk-Free Rates

The system includes realistic default risk-free rates for major currencies:

| Currency | Default Rate | Currency | Default Rate |
|----------|-------------|----------|-------------|
| USD      | 3.00%       | EUR      | 2.50%       |
| GBP      | 3.50%       | JPY      | 1.00%       |
| CHF      | 2.00%       | CAD      | 3.00%       |
| AUD      | 3.50%       | NZD      | 4.00%       |
| SEK      | 3.00%       | NOK      | 3.50%       |
| DKK      | 2.50%       | PLN      | 4.00%       |
| CZK      | 3.50%       | HUF      | 5.00%       |
| RUB      | 8.00%       | BRL      | 6.00%       |
| MXN      | 5.00%       | SGD      | 3.00%       |
| HKD      | 3.00%       | INR      | 5.00%       |
| KRW      | 3.00%       | CNY      | 2.50%       |
| TRY      | 8.00%       | ZAR      | 6.00%       |

## Usage Examples

### Basic Usage

```python
from apps.markets.risk_free_rate_service import get_risk_free_rate

# Get risk-free rate for USD
usd_rate = get_risk_free_rate('USD')
print(f"USD risk-free rate: {usd_rate:.4f}")

# Get risk-free rate for EUR
eur_rate = get_risk_free_rate('EUR')
print(f"EUR risk-free rate: {eur_rate:.4f}")
```

### YTD Risk-Free Rates

```python
from apps.markets.risk_free_rate_service import get_risk_free_rate_for_ytd

# Get YTD risk-free rate for USD
usd_ytd_rate = get_risk_free_rate_for_ytd('USD')
print(f"USD YTD risk-free rate: {usd_ytd_rate:.4f}")
```

### Currency-Specific Sharpe Ratios

```python
from apps.markets.metrics import calculate_sharpe_ratio

# Calculate Sharpe ratio with USD risk-free rate
usd_sharpe = calculate_sharpe_ratio(returns, frequency=252, currency='USD')

# Calculate Sharpe ratio with EUR risk-free rate
eur_sharpe = calculate_sharpe_ratio(returns, frequency=252, currency='EUR')
```

### Chart Service Integration

The chart service automatically uses currency-specific risk-free rates:

```python
from apps.markets.chart_service import get_chart_service

chart_service = get_chart_service()
result = chart_service.compare_assets(
    symbols=['GOOGL'],
    base_currency='USD',
    period='YTD'
)

# Sharpe ratio will automatically use USD risk-free rate
sharpe_ratio = result['metrics']['GOOGL']['sharpe_ratio']
```

## Benefits

1. **More Accurate Sharpe Ratios**: Uses actual market risk-free rates instead of fixed assumptions
2. **Currency Awareness**: Automatically adjusts for different currencies
3. **Real-Time Data**: Fetches current treasury rates when available
4. **Robust Fallbacks**: Gracefully handles API failures with sensible defaults
5. **Performance**: Caching reduces API calls and improves response times
6. **Extensibility**: Easy to add new currencies or data sources

## Testing

The implementation includes comprehensive testing that verifies:
- Risk-free rate service functionality
- Currency-specific Sharpe ratio calculations
- Chart service integration
- Multi-currency support
- Fallback mechanisms

Run the demo script to see the functionality in action:
```bash
python examples/risk_free_rate_demo.py
```

## Future Enhancements

1. **Additional Data Sources**: Integrate with ECB, Bank of England, or other central bank APIs
2. **Real-Time Updates**: WebSocket connections for live rate updates
3. **Historical Rate Analysis**: Track risk-free rate changes over time
4. **Custom Rate Overrides**: Allow users to specify custom risk-free rates
5. **Rate Interpolation**: Smooth rate curves for different maturities
