from __future__ import annotations

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_home(client):
    r = client.get("/")
    assert r.status_code == 200


@pytest.mark.django_db
def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200

