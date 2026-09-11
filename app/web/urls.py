from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from app.web import quiz_views, review_views, scan_views, views

urlpatterns = [
    path("", quiz_views.quiz_list, name="dashboard"),
    path("healthz", views.healthz, name="healthz"),
    path(
        "accounts/login/",
        LoginView.as_view(template_name="registration/login.html", redirect_authenticated_user=True),
        name="login",
    ),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("accounts/register/", views.register, name="register"),
    # No password-reset routes. Recovery is via Django admin (§2 R0.1 / §6 Q13a).
    # --- Quizzes (Phase 8.1) ---
    path("quizzes/new", quiz_views.quiz_create, name="quiz_create"),
    path("quizzes/<int:pk>/", quiz_views.quiz_detail, name="quiz_detail"),
    path("quizzes/<int:pk>/upload", quiz_views.quiz_upload, name="quiz_upload"),
    path("quizzes/<int:pk>/versions/generate", quiz_views.version_generate, name="version_generate"),
    path("quizzes/<int:pk>/edit", quiz_views.quiz_edit, name="quiz_edit"),
    path("quizzes/<int:pk>/delete", quiz_views.quiz_delete, name="quiz_delete"),
    path("quizzes/<int:pk>/results", quiz_views.quiz_results, name="quiz_results"),
    path("quizzes/<int:pk>/results.csv", quiz_views.quiz_results_csv, name="quiz_results_csv"),
    path("versions/<int:pk>/<str:kind>.pdf", quiz_views.version_pdf, name="version_pdf"),
    # --- Review + audit (Phase 9) ---
    path("submissions/<int:pk>/", review_views.submission_detail, name="submission_detail"),
    path("submissions/<int:pk>/assign", review_views.submission_assign, name="submission_assign"),
    path("answers/<int:pk>/override", review_views.answer_override, name="answer_override"),
    path("quizzes/<int:pk>/roster", review_views.quiz_roster, name="quiz_roster"),
    path("versions/<int:pk>/mark-printed", review_views.version_mark_printed, name="version_mark_printed"),
    # --- Scan intake (Phase 7) ---
    path("versions/<int:pk>/submissions/upload", scan_views.submission_upload, name="submission_upload"),
    path(
        "versions/<int:pk>/submissions/upload-batch",
        scan_views.submission_upload_batch,
        name="submission_upload_batch",
    ),
]
