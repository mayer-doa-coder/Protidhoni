"""One-time, fail-closed migration for pre-encryption sensitive reports.

Older Phase 1 databases can contain plaintext SOS/MEDICAL_NEED rows. Current
code expects those fields to be Fernet ciphertext, so reading a mixed-age
database fails. This command classifies every sensitive row before changing
anything and performs all requested updates in one database transaction.

Run without ``--apply`` first. The command prints counts only; report content
and encryption keys are never written to output.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from . import encryption
from .config import get_settings
from .models import Report

StorageState = Literal["legacy_plaintext", "encrypted"]

_SELECT_SENSITIVE_REPORTS = """
SELECT message_id, report_type, payload, raw_message
FROM reports
WHERE report_type IN ('SOS', 'MEDICAL_NEED')
ORDER BY message_id
"""

_UPDATE_SENSITIVE_REPORT = """
UPDATE reports
SET payload = %(payload)s,
    raw_message = %(raw_message)s,
    location = CASE
        WHEN %(lat)s::double precision IS NULL OR %(lng)s::double precision IS NULL THEN NULL
        ELSE ST_SetSRID(
            ST_MakePoint(%(lng)s::double precision, %(lat)s::double precision), 4326
        )::geography
    END
WHERE message_id = %(message_id)s::uuid
  AND raw_message = %(original_raw_message)s
RETURNING message_id
"""


class LegacyEncryptionMigrationError(RuntimeError):
    """A row cannot be migrated without risking disclosure or corruption."""


@dataclass(frozen=True)
class MigrationSummary:
    scanned: int
    legacy_plaintext: int
    already_encrypted: int
    migrated: int


def _looks_like_fernet_envelope(value: object) -> bool:
    """Recognize a Fernet envelope without needing the encryption key.

    The prefix check deliberately treats damaged Fernet-looking values as
    ciphertext. Such a value must fail decryption instead of being encrypted a
    second time and made unrecoverable.
    """
    if not isinstance(value, str):
        return False
    if value.startswith("gAAAA") and len(value) >= 80:
        return True
    try:
        decoded = base64.urlsafe_b64decode(value.encode("ascii"))
    except (UnicodeEncodeError, binascii.Error, ValueError):
        return False
    return len(decoded) >= 73 and decoded[0] == 0x80


def classify_sensitive_storage(raw_message: Mapping[str, object]) -> StorageState:
    """Classify one sensitive report, validating either representation fully."""
    report_type = raw_message.get("type")
    if report_type not in encryption.SENSITIVE_REPORT_TYPES:
        raise LegacyEncryptionMigrationError("migration received a non-sensitive report")

    try:
        payload = raw_message["payload"]
        location = raw_message["location"]
        if not isinstance(payload, Mapping) or not isinstance(location, Mapping):
            raise TypeError
        values = [payload["text"]]
        values.extend(value for value in (location["lat"], location["lng"]) if value is not None)
    except (KeyError, TypeError) as error:
        raise LegacyEncryptionMigrationError("sensitive report structure is invalid") from error

    envelope_flags = [_looks_like_fernet_envelope(value) for value in values]
    if all(envelope_flags):
        restored = encryption.decrypt_sensitive_report_dict(dict(raw_message), str(report_type))
        try:
            Report.model_validate(restored)
        except ValidationError as error:
            raise LegacyEncryptionMigrationError(
                "decrypted sensitive report does not satisfy the report schema"
            ) from error
        return "encrypted"

    if any(envelope_flags):
        raise LegacyEncryptionMigrationError(
            "sensitive report mixes plaintext and ciphertext fields"
        )

    try:
        Report.model_validate(dict(raw_message))
    except ValidationError as error:
        raise LegacyEncryptionMigrationError(
            "legacy plaintext report does not satisfy the report schema"
        ) from error
    return "legacy_plaintext"


def _migration_params(row: Mapping[str, object]) -> dict[str, object] | None:
    raw_value = row.get("raw_message")
    payload_value = row.get("payload")
    if not isinstance(raw_value, Mapping) or not isinstance(payload_value, Mapping):
        raise LegacyEncryptionMigrationError("stored report JSON is invalid")

    raw_message = dict(raw_value)
    report_type = row.get("report_type")
    if report_type != raw_message.get("type"):
        raise LegacyEncryptionMigrationError("report_type disagrees with raw_message.type")
    if dict(payload_value) != raw_message.get("payload"):
        raise LegacyEncryptionMigrationError("payload disagrees with raw_message.payload")

    if classify_sensitive_storage(raw_message) == "encrypted":
        return None

    encrypted = encryption.encrypt_sensitive_report_dict(raw_message, str(report_type))
    location = raw_message["location"]
    if not isinstance(location, Mapping):  # Already schema-validated; keeps typing explicit.
        raise LegacyEncryptionMigrationError("legacy report location is invalid")
    return {
        "message_id": row["message_id"],
        "payload": Jsonb(encrypted["payload"]),
        "raw_message": Jsonb(encrypted),
        "original_raw_message": Jsonb(raw_message),
        "lat": encryption.location_coordinate_for_query_index(location["lat"], str(report_type)),
        "lng": encryption.location_coordinate_for_query_index(location["lng"], str(report_type)),
    }


def migrate_connection(connection: psycopg.Connection, *, apply: bool) -> MigrationSummary:
    """Inspect or atomically migrate all sensitive rows on one connection."""
    query = _SELECT_SENSITIVE_REPORTS + (" FOR UPDATE" if apply else "")
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()

        plans: list[dict[str, object]] = []
        already_encrypted = 0
        for row in rows:
            try:
                params = _migration_params(row)
            except (encryption.EncryptionKeyError, LegacyEncryptionMigrationError) as error:
                raise LegacyEncryptionMigrationError(
                    f"report {row.get('message_id')} cannot be migrated: {error}"
                ) from error
            if params is None:
                already_encrypted += 1
            else:
                plans.append(params)

        migrated = 0
        if apply:
            for params in plans:
                cursor.execute(_UPDATE_SENSITIVE_REPORT, params)
                if cursor.fetchone() is None:
                    raise LegacyEncryptionMigrationError(
                        f"report {params['message_id']} changed during migration"
                    )
                migrated += 1

    return MigrationSummary(
        scanned=len(rows),
        legacy_plaintext=len(plans),
        already_encrypted=already_encrypted,
        migrated=migrated,
    )


def _print_summary(summary: MigrationSummary, *, apply: bool) -> None:
    mode = "APPLY" if apply else "DRY RUN"
    print(f"Legacy encryption migration ({mode})")
    print(f"Sensitive rows scanned: {summary.scanned}")
    print(f"Legacy plaintext rows: {summary.legacy_plaintext}")
    print(f"Already encrypted rows: {summary.already_encrypted}")
    print(f"Rows migrated: {summary.migrated}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Encrypt eligible legacy rows in one transaction. Default is a read-only dry run.",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.database_url:
        print("Migration aborted: PROTIDHONI_DATABASE_URL is not configured.", file=sys.stderr)
        return 2

    try:
        encryption.validate_encryption_key()
        with psycopg.connect(settings.database_url) as connection:
            summary = migrate_connection(connection, apply=args.apply)
        _print_summary(summary, apply=args.apply)
    except (encryption.EncryptionKeyError, LegacyEncryptionMigrationError, psycopg.Error) as error:
        print(f"Migration aborted: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
