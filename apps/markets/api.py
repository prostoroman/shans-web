"""
Market API views for DRF v1 endpoints.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from typing import Optional
from django.http import JsonResponse
from django.utils.translation import gettext_lazy as _
from django.db import models
import logging

from apps.data.services import get_instrument_data
from apps.markets.metrics import calculate_metrics
from django.conf import settings
from apps.core.throttling import PlanRateThrottle, BasicAnonThrottle
from apps.data import fmp_client
from django.core.cache import cache
from uuid import uuid4
from threading import Thread
from apps.markets.ai_analysis import build_data_contract
from apps.markets.llm import generate_asset_summary
from apps.data.models import Exchange, Commodity


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
        base_currency = serializers.CharField(max_length=3, default='USD')
        include_dividends = serializers.BooleanField(default=True)
        period = serializers.CharField(max_length=10, default='1Y')
        normalize_mode = serializers.CharField(max_length=20, default='index100')

    def post(self, request):
        payload = self.Payload(data=request.data)
        payload.is_valid(raise_exception=True)
        
        symbol_list = [s.upper() for s in payload.validated_data['symbols']]
        base_currency = payload.validated_data['base_currency'].upper()
        include_dividends = payload.validated_data['include_dividends']
        period = payload.validated_data['period']
        normalize_mode = payload.validated_data['normalize_mode']

        if not symbol_list:
            return Response({'error': _('Symbols parameter is required')}, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate base currency
        from .smart_currency_converter import get_smart_currency_converter
        currency_converter = get_smart_currency_converter()
        if not currency_converter.is_currency_supported(base_currency):
            return Response(
                {'error': _('Unsupported currency: {}').format(base_currency)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Use the new comparison service
            from .comparison_service import get_comparison_service
            
            comparison_service = get_comparison_service()
            comparison_result = comparison_service.compare_assets(
                symbol_list, 
                base_currency=base_currency,
                include_dividends=include_dividends,
                period=period,
                normalize_mode=normalize_mode
            )
            
            if 'error' in comparison_result:
                return Response(
                    {'error': comparison_result['error']},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            return Response(comparison_result)
            
        except Exception as e:
            logger.error(f"Error in compare API: {e}")
            return Response(
                {'error': _('Error processing comparison request')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def get(self, request):
        return Response({'error': _('Symbols parameter is required')}, status=status.HTTP_400_BAD_REQUEST)


class CommoditiesAPIView(APIView):
    """GET /api/v1/commodities/<symbol> - Get commodities quote data"""
    throttle_classes = [PlanRateThrottle, BasicAnonThrottle]

    def get(self, request, symbol: str = ""):
        symbol = (symbol or request.GET.get('symbol', '')).upper()
        
        if not symbol:
            return Response(
                {'error': _('Symbol parameter is required')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Get commodities quote data
            quote_data = fmp_client.get_commodities_quote(symbol)
            if not quote_data:
                return Response(
                    {'error': _('Commodity symbol not found')},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Format response data similar to MarketAPIView for consistency
            response_data = {
                'symbol': quote_data.get('symbol', symbol),
                'name': quote_data.get('name', symbol),
                
                'quote': {
                    'price': quote_data.get('price'),
                    'changesPercentage': quote_data.get('changePercentage'),
                    'change': quote_data.get('change'),
                    'dayLow': quote_data.get('dayLow'),
                    'dayHigh': quote_data.get('dayHigh'),
                    'volume': quote_data.get('volume'),
                    'marketCap': quote_data.get('marketCap'),
                    'exchange': quote_data.get('exchange', 'Commodity Exchange'),
                },
                
                'profile': {
                    'name': quote_data.get('name', symbol),
                    'exchange': quote_data.get('exchange', 'Commodity Exchange'),
                    'currency': 'USD',  # Most commodities are in USD
                    'stockType': 'Commodity',
                },
            }
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Error in commodities API for {symbol}: {e}")
            return Response(
                {'error': _('Internal server error')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CommoditiesSearchAPIView(APIView):
    """GET /api/v1/commodities/search?q=<query> - Search available commodities"""
    throttle_classes = [PlanRateThrottle, BasicAnonThrottle]

    def get(self, request):
        query = request.GET.get('q', '').strip()
        
        try:
            # Search commodities
            commodities = fmp_client.search_commodities(query)
            
            response_data = {
                'query': query,
                'commodities': commodities,
                'count': len(commodities),
            }
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Error in commodities search API for {query}: {e}")
            return Response(
                {'error': _('Internal server error')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ForexAPIView(APIView):
    """GET /api/v1/forex/<symbol> - Get forex quote data"""
    throttle_classes = [PlanRateThrottle, BasicAnonThrottle]

    def get(self, request, symbol: str = ""):
        symbol = (symbol or request.GET.get('symbol', '')).upper()
        
        if not symbol:
            return Response(
                {'error': _('Symbol parameter is required')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Get forex quote data
            quote_data = fmp_client.get_forex_quote(symbol)
            if not quote_data:
                return Response(
                    {'error': _('Forex symbol not found')},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Format response data similar to MarketAPIView for consistency
            response_data = {
                'symbol': quote_data.get('symbol', symbol),
                'name': quote_data.get('name', symbol),
                
                'quote': {
                    'price': quote_data.get('price'),
                    'changesPercentage': quote_data.get('changePercentage'),
                    'change': quote_data.get('change'),
                    'dayLow': quote_data.get('dayLow'),
                    'dayHigh': quote_data.get('dayHigh'),
                    'volume': quote_data.get('volume'),
                    'exchange': quote_data.get('exchange', 'Forex Exchange'),
                },
                
                'profile': {
                    'name': quote_data.get('name', symbol),
                    'exchange': quote_data.get('exchange', 'Forex Exchange'),
                    'currency': 'USD',  # Most forex pairs are quoted against USD
                    'stockType': 'Forex',
                },
            }
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Error in forex API for {symbol}: {e}")
            return Response(
                {'error': _('Internal server error')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ForexSearchAPIView(APIView):
    """GET /api/v1/forex/search?q=<query> - Search available forex currency pairs"""
    throttle_classes = [PlanRateThrottle, BasicAnonThrottle]

    def get(self, request):
        query = request.GET.get('q', '').strip()
        
        try:
            # Search forex currency pairs
            forex_pairs = fmp_client.search_forex(query)
            
            response_data = {
                'query': query,
                'forex_pairs': forex_pairs,
                'count': len(forex_pairs),
            }
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Error in forex search API for {query}: {e}")
            return Response(
                {'error': _('Internal server error')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class SymbolSearchAPIView(APIView):
    """GET /api/v1/search?q=<query> - Optimized symbol search using FMP unified search endpoint"""
    # Temporarily disable throttling for development
    throttle_classes = []

    def get(self, request):
        query = request.GET.get('q', '').strip()
        limit = min(int(request.GET.get('limit', 20)), 50)  # Cap at 50 results
        
        if not query or len(query) < 2:
            return Response({
                'query': query,
                'results': [],
                'count': 0,
                'message': _('Please enter at least 2 characters to search')
            })
        
        try:
            results = []
            query_upper = query.upper()
            
            # 1. Check if query looks like an ISIN (12 alphanumeric characters)
            if len(query) == 12 and query.isalnum():
                try:
                    isin_results = fmp_client.search_by_isin(query)
                    for item in isin_results[:limit]:
                        symbol = item.get('symbol', '')
                        if symbol:
                            # Get profile for additional data
                            profile = fmp_client.get_profile(symbol)
                            if profile:
                                asset_type = 'etf' if profile.get('isEtf') or profile.get('isFund') else 'stock'
                                results.append({
                                    'symbol': symbol,
                                    'name': profile.get('companyName', item.get('name', '')),
                                    'currency': profile.get('currency', item.get('currency', 'USD')),
                                    'exchangeFullName': profile.get('exchange', item.get('exchange', '')),
                                    'exchange': profile.get('exchange', item.get('exchange', '')),
                                    'type': asset_type,
                                    'score': 100  # ISIN search gets highest priority
                                })
                            else:
                                # Fallback if profile lookup fails
                                results.append({
                                    'symbol': symbol,
                                    'name': item.get('name', ''),
                                    'currency': item.get('currency', 'USD'),
                                    'exchangeFullName': item.get('exchange', ''),
                                    'exchange': item.get('exchange', ''),
                                    'type': 'stock',
                                    'score': 95
                                })
                except Exception as e:
                    logger.warning(f"Error searching ISIN for {query}: {e}")
            
            # 2. Use unified search for comprehensive results (NEW APPROACH)
            if not results:
                try:
                    unified_results = fmp_client.unified_search(query, limit=limit)
                    
                    # Enhance results with additional data and scoring
                    for item in unified_results:
                        symbol = item.get('symbol', '')
                        if symbol:
                            # Boost score for exact symbol matches
                            score = item.get('score', 50)
                            if symbol.upper() == query_upper:
                                score = max(score, 100)
                            elif symbol.upper().startswith(query_upper):
                                score = max(score, 90)
                            
                            # Get additional profile data for stocks/ETFs
                            if item.get('type') in ['stock', 'etf']:
                                try:
                                    profile = fmp_client.get_profile(symbol)
                                    if profile:
                                        item['name'] = profile.get('companyName', item.get('name', ''))
                                        item['currency'] = profile.get('currency', item.get('currency', 'USD'))
                                        item['exchangeFullName'] = profile.get('exchange', item.get('exchange', ''))
                                        item['exchange'] = profile.get('exchange', item.get('exchange', ''))
                                        # Update asset type based on profile
                                        if profile.get('isEtf') or profile.get('isFund'):
                                            item['type'] = 'etf'
                                        else:
                                            item['type'] = 'stock'
                                except Exception:
                                    pass  # Use original data if profile lookup fails
                            
                            item['score'] = score
                            results.append(item)
                            
                except Exception as e:
                    logger.warning(f"Error in unified search for {query}: {e}")
            
            # 3. Fallback: Try individual searches if unified search fails or returns few results
            if len(results) < 5:
                try:
                    # Try commodities search from database
                    commodities = Commodity.objects.filter(
                        is_active=True
                    ).filter(
                        models.Q(symbol__icontains=query) | 
                        models.Q(name__icontains=query)
                    )[:5]  # Limit to 5 commodities
                    
                    for commodity in commodities:
                        # Check if already in results
                        if not any(r.get('symbol') == commodity.symbol for r in results):
                            results.append({
                                'symbol': commodity.symbol,
                                'name': commodity.name,
                                'currency': commodity.currency,
                                'exchange': 'COMMODITY',
                                'exchangeFullName': 'Commodity Exchange',
                                'type': 'commodity',
                                'score': 98 if commodity.symbol.upper() == query_upper else 90
                            })
                except Exception as e:
                    logger.warning(f"Error searching commodities for {query}: {e}")
                
                # Try forex search from database
                try:
                    from apps.data.models import Forex
                    from django.db.models import Q
                    
                    forex_pairs = Forex.objects.filter(
                        Q(symbol__icontains=query) | 
                        Q(name__icontains=query) |
                        Q(from_currency__icontains=query) |
                        Q(to_currency__icontains=query) |
                        Q(from_name__icontains=query) |
                        Q(to_name__icontains=query)
                    ).filter(is_active=True)[:5]
                    
                    for pair in forex_pairs:
                        # Check if already in results
                        if not any(r.get('symbol') == pair.symbol for r in results):
                            results.append({
                                'symbol': pair.symbol,
                                'name': pair.name,
                                'currency': pair.to_currency or pair.quote_currency,
                                'exchange': 'FOREX',
                                'exchangeFullName': 'Foreign Exchange',
                                'type': 'forex',
                                'score': 95 if pair.symbol.upper() == query_upper else 85,
                                'base_currency': pair.base_currency,
                                'quote_currency': pair.quote_currency,
                                'from_currency': pair.from_currency,
                                'to_currency': pair.to_currency,
                                'from_name': pair.from_name,
                                'to_name': pair.to_name,
                            })
                except Exception as e:
                    logger.warning(f"Error searching forex for {query}: {e}")
            
            # Sort by score (highest first) and limit results
            results.sort(key=lambda x: x.get('score', 0), reverse=True)
            results = results[:limit]
            
            # Get categories for filtering
            categories = {}
            for result in results:
                asset_type = result.get('type', '')
                if asset_type:
                    # Convert to plural form for consistency with frontend
                    if asset_type == 'stock':
                        categories['stocks'] = categories.get('stocks', 0) + 1
                    elif asset_type == 'etf':
                        categories['etfs'] = categories.get('etfs', 0) + 1
                    elif asset_type == 'commodity':
                        categories['commodities'] = categories.get('commodities', 0) + 1
                    elif asset_type == 'cryptocurrency':
                        categories['cryptocurrencies'] = categories.get('cryptocurrencies', 0) + 1
                    elif asset_type == 'forex':
                        categories['forex'] = categories.get('forex', 0) + 1
            
            return Response({
                'query': query,
                'results': results,
                'count': len(results),
                'categories': categories
            })
            
        except Exception as e:
            logger.error(f"Error in symbol search for {query}: {e}")
            return Response({
                'query': query,
                'results': [],
                'count': 0,
                'error': _('Search failed. Please try again.')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ExchangeAPIView(APIView):
    """GET /api/v1/exchanges/ - Get list of available exchanges"""
    throttle_classes = [PlanRateThrottle, BasicAnonThrottle]

    def get(self, request):
        try:
            exchanges = Exchange.objects.filter(is_active=True).order_by('name')
            
            exchange_data = []
            for exchange in exchanges:
                exchange_data.append({
                    'code': exchange.code,
                    'name': exchange.name,
                    'country_name': exchange.country_name,
                    'country_code': exchange.country_code,
                    'symbol_suffix': exchange.symbol_suffix,
                    'delay': exchange.delay,
                })
            
            return Response({
                'exchanges': exchange_data,
                'count': len(exchange_data)
            })
            
        except Exception as e:
            logger.error(f"Error in exchange API: {e}")
            return Response({
                'exchanges': [],
                'count': 0,
                'error': _('Failed to fetch exchanges')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ------------------------------- AI Summary APIs -------------------------------

AI_SUMMARY_TTL_SECONDS = 24 * 60 * 60  # 24 hours for result cache
AI_JOB_TTL_SECONDS = 30 * 60  # 30 minutes for progress


def _ai_job_key(job_id: str) -> str:
    return f"ai:job:{job_id}"


def _ai_result_key(symbol: str) -> str:
    return f"ai:summary:{symbol.upper()}"


def _update_job(job_id: str, status_text: str, percent: int, extra: Optional[dict] = None) -> None:
    current = cache.get(_ai_job_key(job_id)) or {}
    updated = {"status": status_text, "percent": percent}
    if isinstance(current, dict):
        updated = {**current, **updated}
    if extra:
        updated.update(extra)
    cache.set(_ai_job_key(job_id), updated, AI_JOB_TTL_SECONDS)


def _run_ai_pipeline(job_id: str, symbol: str) -> None:
    try:
        sym = symbol.upper()
        _update_job(job_id, "Identifying asset...", 5)
        data = build_data_contract(sym)

        _update_job(job_id, "Preparing calculations...", 35)
        # calculations are part of data-contract already

        _update_job(job_id, "Summarizing with AI...", 65)
        summary = generate_asset_summary(data) or ""

        _update_job(job_id, "Finalizing...", 90)
        payload = {"symbol": sym, "data": data, "summary": summary}
        cache.set(_ai_result_key(sym), payload, AI_SUMMARY_TTL_SECONDS)
        _update_job(job_id, "completed", 100)
    except Exception as e:  # noqa: BLE001
        logger.error(f"AI pipeline failed for {symbol}: {e}")
        cache.set(_ai_job_key(job_id), {"status": "failed", "percent": 100, "error": str(e)}, AI_JOB_TTL_SECONDS)


class AISummaryStartAPIView(APIView):
    """POST /api/v1/ai/summary/start?symbol=..."""
    throttle_classes = [PlanRateThrottle, BasicAnonThrottle]

    def _start(self, symbol: str):
        symbol = symbol.upper()
        # If cached summary exists, return completed immediately
        existing = cache.get(_ai_result_key(symbol))
        if existing:
            job_id = str(uuid4())
            _update_job(job_id, "completed", 100, {"symbol": symbol})
            return {"job_id": job_id, "status": "completed", "result": existing}

        job_id = str(uuid4())
        _update_job(job_id, "queued", 0, {"symbol": symbol})
        t = Thread(target=_run_ai_pipeline, args=(job_id, symbol), daemon=True)
        t.start()
        return {"job_id": job_id, "status": "queued"}

    def post(self, request):
        symbol = (request.GET.get('symbol') or request.data.get('symbol') or '').upper()
        if not symbol:
            return Response({'error': _('Symbol parameter is required')}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self._start(symbol))

    def get(self, request):
        symbol = (request.GET.get('symbol') or '').upper()
        if not symbol:
            return Response({'error': _('Symbol parameter is required')}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self._start(symbol))


class AISummaryStatusAPIView(APIView):
    """GET /api/v1/ai/summary/status?job_id=..."""
    throttle_classes = [PlanRateThrottle, BasicAnonThrottle]

    def get(self, request):
        job_id = (request.GET.get('job_id') or '').strip()
        if not job_id:
            return Response({'error': _('job_id is required')}, status=status.HTTP_400_BAD_REQUEST)
        job = cache.get(_ai_job_key(job_id))
        if not job:
            return Response({'error': _('job not found')}, status=status.HTTP_404_NOT_FOUND)
        # Return result as well when completed
        result = None
        if job.get('status') == 'completed':
            symbol = request.GET.get('symbol') or job.get('symbol')
            if symbol:
                result = cache.get(_ai_result_key(str(symbol).upper()))
        return Response({"job_id": job_id, **job, "result": result})


class AISummaryGetAPIView(APIView):
    """GET /api/v1/ai/summary/<symbol> - return cached result if exists"""
    throttle_classes = [PlanRateThrottle, BasicAnonThrottle]

    def get(self, request, symbol: str = ""):
        sym = (symbol or request.GET.get('symbol') or '').upper()
        if not sym:
            return Response({'error': _('Symbol parameter is required')}, status=status.HTTP_400_BAD_REQUEST)
        existing = cache.get(_ai_result_key(sym))
        if not existing:
            return Response({'error': _('No cached summary for this symbol')}, status=status.HTTP_404_NOT_FOUND)
        return Response(existing)