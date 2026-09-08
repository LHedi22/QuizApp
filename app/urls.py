from django.contrib import admin
from django.urls import path

from app.web import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", views.healthz, name="healthz"),
]
