"""DB-level enforcement of the immutability rules (decision D4).

- `core_version`: block any UPDATE that changes question_order / option_order / qr_id
  (REBUILD_SPEC §2 R2.7). `printed_at` and other columns stay editable.
- `core_auditevent`: block every UPDATE (append-only, R6.5).

DELETE is intentionally NOT blocked: cascade on a whole-quiz teardown and the R1.5
"discard versions before re-upload" path (only while nothing is printed) both need
it. Version deletion is gated in application logic.
"""

from django.db import migrations

_FORWARD = r"""
CREATE OR REPLACE FUNCTION quizscan_block_version_map_update() RETURNS trigger AS $$
BEGIN
    IF (NEW.question_order IS DISTINCT FROM OLD.question_order)
        OR (NEW.option_order IS DISTINCT FROM OLD.option_order)
        OR (NEW.qr_id IS DISTINCT FROM OLD.qr_id) THEN
        RAISE EXCEPTION
            'core_version.question_order/option_order/qr_id are immutable after creation (R2.7)';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER quizscan_version_maps_immutable
    BEFORE UPDATE ON core_version
    FOR EACH ROW EXECUTE FUNCTION quizscan_block_version_map_update();

CREATE OR REPLACE FUNCTION quizscan_block_audit_update() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'core_auditevent is append-only (R6.5)';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER quizscan_auditevent_append_only
    BEFORE UPDATE ON core_auditevent
    FOR EACH ROW EXECUTE FUNCTION quizscan_block_audit_update();
"""

_REVERSE = r"""
DROP TRIGGER IF EXISTS quizscan_version_maps_immutable ON core_version;
DROP FUNCTION IF EXISTS quizscan_block_version_map_update();
DROP TRIGGER IF EXISTS quizscan_auditevent_append_only ON core_auditevent;
DROP FUNCTION IF EXISTS quizscan_block_audit_update();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]

    operations = [migrations.RunSQL(sql=_FORWARD, reverse_sql=_REVERSE)]
