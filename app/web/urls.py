from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from app.web import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("healthz", views.healthz, name="healthz"),
    path(
        "accounts/login/",
        LoginView.as_view(template_name="registration/login.html", redirect_authenticated_user=True),
        name="login",
    ),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("accounts/register/", views.register, name="register"),
    # No password-reset routes. Recovery is via Django admin (§2 R0.1 / §6 Q13a).
]
