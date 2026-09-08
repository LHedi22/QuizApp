"""Phase 1.3 DoD: self-signup + login + session, and NO password-reset flow
(REBUILD_SPEC §2 R0.1, R0.3; §6 Q13a)."""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import NoReverseMatch, reverse

pytestmark = pytest.mark.django_db

STRONG_PW = "tR7$kw9Lq2vz"


def test_register_creates_account_logs_in_and_reaches_dashboard(client):
    resp = client.post(
        "/accounts/register/",
        {"email": "New@Example.com", "password1": STRONG_PW, "password2": STRONG_PW},
    )
    assert resp.status_code == 302
    user = get_user_model().objects.get(email="new@example.com")  # normalized lower
    assert user.check_password(STRONG_PW)
    assert client.get("/").status_code == 200  # dashboard, now authenticated


def test_login_then_logout_cycle(client, professor):
    assert client.login(email="prof@example.com", password="pw-12345")
    assert client.get("/").status_code == 200
    client.post("/accounts/logout/")
    r = client.get("/")
    assert r.status_code == 302
    assert "/accounts/login/" in r["Location"]


def test_unauthenticated_dashboard_redirects_to_login_before_any_data(client):
    r = client.get("/")
    assert r.status_code == 302
    assert "/accounts/login/" in r["Location"]


def test_duplicate_email_is_rejected(client):
    payload = {"email": "dup@example.com", "password1": STRONG_PW, "password2": STRONG_PW}
    assert client.post("/accounts/register/", payload).status_code == 302
    client.post("/accounts/logout/")
    resp = client.post("/accounts/register/", payload)
    assert resp.status_code == 200  # re-rendered with an error
    assert b"already exists" in resp.content
    assert get_user_model().objects.filter(email="dup@example.com").count() == 1


def test_weak_password_is_rejected(client):
    resp = client.post(
        "/accounts/register/",
        {"email": "weak@example.com", "password1": "password", "password2": "password"},
    )
    assert resp.status_code == 200
    assert not get_user_model().objects.filter(email="weak@example.com").exists()


def test_password_mismatch_is_rejected(client):
    resp = client.post(
        "/accounts/register/",
        {"email": "mm@example.com", "password1": STRONG_PW, "password2": STRONG_PW + "x"},
    )
    assert resp.status_code == 200
    assert not get_user_model().objects.filter(email="mm@example.com").exists()


@pytest.mark.parametrize(
    "name",
    ["password_reset", "password_reset_done", "password_reset_confirm", "password_change"],
)
def test_no_password_reset_url_names(name):
    with pytest.raises(NoReverseMatch):
        reverse(name)


@pytest.mark.parametrize(
    "path",
    [
        "/accounts/password_reset/",
        "/accounts/password/reset/",
        "/password_reset/",
        "/accounts/password_change/",
    ],
)
def test_no_password_reset_paths(client, path):
    assert client.get(path).status_code == 404
