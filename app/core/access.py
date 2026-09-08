"""The single funnel every data view uses to fetch an object (REBUILD_SPEC §2 R0.2).

A professor may only ever read/modify their own data; a foreign id must look
*missing*, not *forbidden* (a 404, never a 403 — R0.2). Views must never call
`Model.objects.get(pk=...)` directly on owned models — always `get_owned_or_404`.
"""

from __future__ import annotations

from django.http import Http404


def get_owned_or_404(model, pk, user):
    """Return the `model` row `pk` iff it belongs to `user`, else raise `Http404`."""
    try:
        return model.objects.owned_by(user).get(pk=pk)
    except model.DoesNotExist as exc:
        raise Http404(f"{model.__name__} {pk} not found") from exc
