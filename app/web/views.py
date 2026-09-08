from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render

from app.web.forms import RegisterForm


def healthz(_request: HttpRequest) -> JsonResponse:
    """Liveness probe. No DB access — answers even if Postgres is down."""
    return JsonResponse({"status": "ok"})


def register(request: HttpRequest) -> HttpResponse:
    """Open self-signup (R0.1): no allowlist, no invite, no approval gate."""
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("dashboard")
    return render(request, "web/register.html", {"form": form})


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    return render(request, "web/dashboard.html")
