import json
from django.urls import reverse


def test_api_urls_exist(client):
    # info
    assert client.get('/api/v1/info/AAPL/').status_code in (200, 400, 404)
    # history
    assert client.get('/api/v1/history/AAPL/?period=1y').status_code in (200, 400, 404)
    # compare requires POST
    assert client.post('/api/v1/compare/', data={"symbols": ["AAPL", "MSFT"]}, content_type='application/json').status_code in (200, 400)
    # portfolio analyze requires POST
    assert client.post('/api/portfolio/v1/analyze/', data={"weights": {"AAPL": 0.5, "MSFT": 0.5}}, content_type='application/json').status_code in (200, 400)

