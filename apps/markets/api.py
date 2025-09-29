"""
Market API views for DRF v1 endpoints.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from django.http import JsonResponse
from django.utils.translation import gettext_lazy as _
import logging

from apps.data.services import get_instrument_data
from apps.markets.metrics import calculate_metrics
from django.conf import settings
from apps.core.throttling import PlanRateThrottle, BasicAnonThrottle
from apps.data import fmp_client


class HistoryAPIView(APIView):
    """GET /api/v1/history/<symbol>?period=5y"""
    throttle_classes = [PlanRateThrottle, BasicAnonThrottle]

    def get(self, request, symbol: str = ""):
        symbol = (symbol or request.GET.get('symbol', '')).upper()
        period = request.GET.get('period', '5y')
        try:
            # Map period to days approx
            years = 1
            if period.endswith('y'):
                years = int(period[:-1])
            days = min(max(years * 365, 30), 3650)
            # fetch series
            from datetime import date, timedelta
            end = date.today()
            start = end - timedelta(days=days)
            hist = fmp_client.get_price_series(symbol, start.isoformat(), end.isoformat())
            prices = [
                {"date": h.get('date'), "close": float(h.get('close'))}
                for h in hist if h.get('date') and h.get('close') is not None
            ]
            return Response({"symbol": symbol, "prices": list(reversed(prices))})
        except Exception as e:  # noqa: BLE001
            logger.error(f"Error in history API for {symbol}: {e}")
            return Response({'error': _('Internal server error')}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ETFHoldingsAPIView(APIView):
    """GET /api/v1/etf/<symbol>/holdings"""
    throttle_classes = [PlanRateThrottle, BasicAnonThrottle]

    def get(self, request, symbol: str = ""):
        symbol = (symbol or request.GET.get('symbol', '')).upper()
        try:
            data = fmp_client.get_etf_holdings(symbol)
            return Response(data)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Error in etf holdings API for {symbol}: {e}")
            return Response({'error': _('Internal server error')}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
logger = logging.getLogger(__name__)


class MarketAPIView(APIView):
    """GET /api/v1/info/<symbol>; legacy GET /api/info/?symbol=..."""
    throttle_classes = [PlanRateThrottle, BasicAnonThrottle]

    def get(self, request, symbol: str = ""):
        symbol = (symbol or request.GET.get('symbol', '')).upper()
        
        if not symbol:
            return Response(
                {'error': _('Symbol parameter is required')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Get instrument data
            data = get_instrument_data(symbol, include_prices=True, include_fundamentals=True)
            if not data:
                return Response(
                    {'error': _('Symbol not found')},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            instrument = data['instrument']
            prices = data['prices']
            fundamentals = data['fundamentals']
            
            # Calculate metrics
            if prices:
                price_values = [float(p.close_price) for p in prices]
                metrics = calculate_metrics(
                    price_values,
                    risk_free_rate=settings.DEFAULT_RF,
                    years=5.0
                )
            else:
                metrics = {}
            
            # Sector percentiles using peers
            peers = fmp_client.get_peers(symbol)[:20]
            percentiles = {}
            if fundamentals and peers:
                # build peer metrics snapshot for PE, ROE, margin, D/E
                import numpy as _np
                values = {
                    'pe': [], 'roe': [], 'margin': [], 'd2e': []
                }
                for peer in peers:
                    km = fmp_client.get_key_metrics(peer) or {}
                    values['pe'].append(float(km.get('peRatio') or km.get('pe') or 0) or 0)
                    values['roe'].append(float(km.get('roe') or 0) or 0)
                    values['margin'].append(float(km.get('netProfitMargin') or km.get('netProfitMarginTTM') or 0) or 0)
                    values['d2e'].append(float(km.get('debtToEquity') or 0) or 0)
                def pct(val, arr):
                    arr = [x for x in arr if x and x == x]
                    if not arr:
                        return None
                    rank = sum(1 for x in arr if x <= val)
                    return round(100 * rank / len(arr))
                percentiles = {
                    'pe': pct(float(fundamentals.pe_ratio or 0), values['pe']),
                    'roe': pct(float(fundamentals.roe or 0), values['roe']),
                    'margin': pct(float(fundamentals.current_ratio or 0), values['margin']),
                    'd2e': pct(float(fundamentals.debt_to_equity or 0), values['d2e']),
                }

            response_data = {
                'profile': {
                    'name': instrument.name,
                    'exchange': instrument.exchange,
                    'currency': instrument.currency,
                },
                'quote': fmp_client.get_quote(symbol) or {},
                'key_metrics': {
                    'pe': float(fundamentals.pe_ratio) if fundamentals and fundamentals.pe_ratio else None,
                    'pb': float(fundamentals.pb_ratio) if fundamentals and fundamentals.pb_ratio else None,
                    'roe': float(fundamentals.roe) if fundamentals and fundamentals.roe else None,
                    'margin': float(fundamentals.current_ratio) if fundamentals and fundamentals.current_ratio else None,
                    'd2e': float(fundamentals.debt_to_equity) if fundamentals and fundamentals.debt_to_equity else None,
                },
                'compact_ratios': {
                    'pe': float(fundamentals.pe_ratio) if fundamentals and fundamentals.pe_ratio else None,
                    'pb': float(fundamentals.pb_ratio) if fundamentals and fundamentals.pb_ratio else None,
                },
                'percentiles': percentiles,
            }
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Error in market API for {symbol}: {e}")
            return Response(
                {'error': _('Internal server error')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CompareAPIView(APIView):
    """POST /api/v1/compare; legacy GET returns 400 for missing symbols"""
    throttle_classes = [PlanRateThrottle, BasicAnonThrottle]

    class Payload(serializers.Serializer):
        symbols = serializers.ListField(child=serializers.CharField(max_length=12), min_length=2, max_length=5)

    def post(self, request):
        payload = self.Payload(data=request.data)
        payload.is_valid(raise_exception=True)
        symbol_list = [s.upper() for s in payload.validated_data['symbols']]

        if not symbol_list:
            return Response({'error': _('Symbols parameter is required')}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Get data for all symbols
            instruments_data = {}
            all_metrics = {}
            
            for symbol in symbol_list:
                data = get_instrument_data(symbol, include_prices=True, include_fundamentals=True)
                if data:
                    instruments_data[symbol] = data
                    
                    # Calculate metrics
                    if data['prices']:
                        price_values = [float(p.close_price) for p in data['prices']]
                        metrics = calculate_metrics(
                            price_values,
                            risk_free_rate=settings.DEFAULT_RF,
                            years=5.0
                        )
                        all_metrics[symbol] = metrics
            
            # Calculate correlation matrix
            correlation_matrix = {}
            if len(symbol_list) >= 2:
                for i, symbol1 in enumerate(symbol_list):
                    for j, symbol2 in enumerate(symbol_list):
                        if i < j and symbol1 in all_metrics and symbol2 in all_metrics:
                            # This is a simplified correlation calculation
                            # In a real implementation, you'd align the price series
                            correlation_matrix[f"{symbol1}_{symbol2}"] = 0.5  # Placeholder
            
            # Prepare response: 5 KPIs per symbol
            compare_data = {}
            for symbol in symbol_list:
                m = all_metrics.get(symbol, {})
                km = fmp_client.get_key_metrics(symbol) or {}
                compare_data[symbol] = {
                    'cagr_5y': m.get('cagr'),
                    'vol': m.get('volatility'),
                    'maxdd': m.get('max_drawdown'),
                    'sharpe': m.get('sharpe_ratio'),
                    'valuation': {
                        'pe': km.get('peRatio') or km.get('pe'),
                        'pb': km.get('priceToBookRatio') or km.get('pb'),
                    },
                    'mini': {
                        'pe_percentile': None,
                        'roe_percentile': None,
                    }
                }
            response_data = {
                'symbols': symbol_list,
                'kpis': compare_data,
                'correlation_matrix': correlation_matrix,
            }
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Error in compare API for {symbol_list}: {e}")
            return Response(
                {'error': _('Internal server error')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def get(self, request):
        return Response({'error': _('Symbols parameter is required')}, status=status.HTTP_400_BAD_REQUEST)