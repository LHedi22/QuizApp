from django.http import HttpRequest, JsonResponse


def healthz(_request: HttpRequest) -> JsonResponse:
    """Liveness probe. No DB access — answers even if Postgres is down."""
    return JsonResponse({"status": "ok"})
