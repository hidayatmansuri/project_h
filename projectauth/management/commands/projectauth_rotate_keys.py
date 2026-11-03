"""
Management command `python manage.py projectauth_rotate_keys` (Section 7 & 13).
Re-encrypts all AES-256-GCM encrypted fields (`TOTPDevice.secret_encrypted`) under the
currently active key (first entry in `PROJECTAUTH_ENCRYPTION_KEYS`).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from projectauth.audit import log_audit
from projectauth.crypto import (
    decrypt,
    encrypt,
    get_active_key_id,
    needs_reencryption,
)
from projectauth.models import TOTPDevice


class Command(BaseCommand):
    help = "Re-encrypts all AES-256-GCM encrypted fields under the active key in PROJECTAUTH_ENCRYPTION_KEYS."

    def handle(self, *args, **options):
        active_kid = get_active_key_id()
        rotated_count = 0
        skipped_count = 0

        with transaction.atomic():
            for device in TOTPDevice.objects.select_for_update().all():
                if needs_reencryption(device.secret_encrypted):
                    plaintext = decrypt(device.secret_encrypted, aad=device.aad)
                    device.secret_encrypted = encrypt(plaintext, aad=device.aad)
                    device.save(update_fields=["secret_encrypted"])
                    rotated_count += 1
                else:
                    skipped_count += 1

        log_audit(
            "crypto.keys_rotated",
            actor_label="cli:projectauth_rotate_keys",
            details={
                "active_key_id": active_kid,
                "rotated_count": rotated_count,
                "skipped_count": skipped_count,
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Key rotation complete (active_key_id='{active_kid}'): "
                f"{rotated_count} re-encrypted, {skipped_count} already current."
            )
        )

