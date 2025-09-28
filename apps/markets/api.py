"""
Market API views for DRF endpoints.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import JsonResponse
from django.utils.translation import gettext_lazy as _
import logging

from apps.data.services import get_instrument_data
from apps.markets.metrics import calculate_metrics
from django.conf import settings

logger = logging.getLogger(__name__)


class MarketAPIView(APIView):
    """Market data API endpoint."""
    
    def get(self, request):
        """Get market data for a symbol."""
        symbol = request.GET.get('symbol', '').upper()
        
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
            
            # Prepare response
            response_data = {
                'symbol': symbol,
                'instrument': {
                    'name': instrument.name,
                    'exchange': instrument.exchange,
                    'sector': instrument.sector,
                    'industry': instrument.industry,
                    'market_cap': instrument.market_cap,
                    'currency': instrument.currency,
                },
                'prices': [
                    {
                        'date': p.date.isoformat(),
                        'open': float(p.open_price),
                        'high': float(p.high_price),
                        'low': float(p.low_price),
                        'close': float(p.close_price),
                        'volume': p.volume,
                        'adjusted_close': float(p.adjusted_close) if p.adjusted_close else None,
                    }
                    for p in prices[:252]  # Last year
                ],
                'fundamentals': {
                    'pe_ratio': float(fundamentals.pe_ratio) if fundamentals and fundamentals.pe_ratio else None,
                    'pb_ratio': float(fundamentals.pb_ratio) if fundamentals and fundamentals.pb_ratio else None,
                    'debt_to_equity': float(fundamentals.debt_to_equity) if fundamentals and fundamentals.debt_to_equity else None,
                    'roe': float(fundamentals.roe) if fundamentals and fundamentals.roe else None,
                    'roa': float(fundamentals.roa) if fundamentals and fundamentals.roa else None,
                    'current_ratio': float(fundamentals.current_ratio) if fundamentals and fundamentals.current_ratio else None,
                } if fundamentals else None,
                'metrics': metrics,
            }
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Error in market API for {symbol}: {e}")
            return Response(
                {'error': _('Internal server error')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CompareAPIView(APIView):
    """Compare symbols API endpoint."""
    
    def get(self, request):
        """Compare multiple symbols."""
        symbols = request.GET.get('symbols', '')
        
        if not symbols:
            return Response(
                {'error': _('Symbols parameter is required')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Parse symbols
        symbol_list = [s.strip().upper() for s in symbols.split(',') if s.strip()]
        
        if len(symbol_list) < 2:
            return Response(
                {'error': _('At least 2 symbols are required for comparison')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
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
            
            # Prepare response
            response_data = {
                'symbols': symbol_list,
                'instruments': {
                    symbol: {
                        'name': data['instrument'].name,
                        'exchange': data['instrument'].exchange,
                        'sector': data['instrument'].sector,
                        'industry': data['instrument'].industry,
                        'market_cap': data['instrument'].market_cap,
                        'currency': data['instrument'].currency,
                    }
                    for symbol, data in instruments_data.items()
                },
                'metrics': all_metrics,
                'correlation_matrix': correlation_matrix,
            }
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Error in compare API for {symbols}: {e}")
            return Response(
                {'error': _('Internal server error')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )