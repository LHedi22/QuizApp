"""Stable text snapshot of the backup-critical state — quiz count, every version's
immutable maps + qr_id, and the SHA-256 of every stored version PDF. Used by
`scripts/check_backup_restore.sh` to prove a restore round-trips byte-for-byte.
"""

from __future__ import annotations

import hashlib
import json
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")
django.setup()

from app.core.blob_storage import get_blob_storage  # noqa: E402
from app.core.models import Quiz, Version  # noqa: E402
from app.pdf.artifacts import version_pdf_paths  # noqa: E402


def main() -> None:
    print(f"quiz={Quiz.objects.count()}")
    storage = get_blob_storage()
    for v in Version.objects.order_by("quiz_id", "version_number"):
        print(
            f"v{v.id} #{v.version_number} qr={v.qr_id} tpl={v.template_version} "
            f"qorder={json.dumps(v.question_order)} "
            f"oorder={json.dumps(v.option_order, sort_keys=True)}"
        )
        for kind, path in sorted(version_pdf_paths(v).items()):
            try:
                digest = hashlib.sha256(storage.read(path)).hexdigest()
            except FileNotFoundError:
                digest = "MISSING"
            print(f"  {kind} {digest}")


if __name__ == "__main__":
    main()
