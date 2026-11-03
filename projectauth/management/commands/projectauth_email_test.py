from django.core.management.base import BaseCommand, CommandError

from projectauth.email_service import diagnose_email_settings, send_projectauth_email


class Command(BaseCommand):
    help = "Send a test email and print a plain-language diagnosis of SMTP/Gmail settings."

    def add_arguments(self, parser):
        parser.add_argument(
            "address",
            type=str,
            help="Destination email address to receive the test email.",
        )

    def handle(self, *args, **options):
        address = (options.get("address") or "").strip()
        if not address or "@" not in address:
            raise CommandError("Please provide a valid email address.")

        self.stdout.write("=== projectauth Email Configuration Diagnosis ===")
        for line in diagnose_email_settings():
            self.stdout.write(f"  - {line}")

        result = send_projectauth_email(
            "email_test",
            [address],
            context={
                "message": "This is a test email from projectauth verifying your email configuration and daily budget guard.",
                "recipient": address,
            },
            subject="Test email configuration check",
            fail_silently=True,
        )

        if result.get("sent"):
            self.stdout.write(
                self.style.SUCCESS(f"Test email dispatched successfully to {address}.")
            )
        else:
            reason = result.get("reason", "unknown")
            err_type = result.get("error_type", "")
            raise CommandError(
                f"Failed to send test email (reason={reason}{', ' + err_type if err_type else ''})."
            )

