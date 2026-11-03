from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models.functions import Lower

from projectauth.crypto import normalize_identifier
from projectauth.sessions import revoke_all_user_sessions
from projectauth.twofa import reset_user_2fa

User = get_user_model()


class Command(BaseCommand):
    help = "Break-glass command to reset all 2FA factors and revoke sessions for a user (audited)."

    def add_arguments(self, parser):
        parser.add_argument(
            "username",
            type=str,
            help="Username (or email) of the account whose 2FA should be reset.",
        )

    def handle(self, *args, **options):
        ident = normalize_identifier(options.get("username") or "")
        if not ident:
            raise CommandError("Please provide a username.")

        user = (
            User.objects.annotate(_ul=Lower("username"), _el=Lower("email"))
            .filter(_ul=ident)
            .first()
            or User.objects.annotate(_el=Lower("email")).filter(_el=ident).first()
        )
        if user is None:
            raise CommandError(f"User '{options['username']}' not found.")

        reset_user_2fa(user, via_cli=True)
        revoked = revoke_all_user_sessions(user)
        self.stdout.write(
            self.style.SUCCESS(
                f"2FA reset complete for '{user.username}' (revoked {revoked} active session(s))."
            )
        )

