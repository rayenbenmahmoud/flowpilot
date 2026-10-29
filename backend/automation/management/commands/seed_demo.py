from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from automation.demo import reset_demo, seed_demo


class Command(BaseCommand):
    help = "Create the demo user, integrations, workflow templates and sample history (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete all workflow data first.")

    def handle(self, *args, **options):
        if not settings.FLOWPILOT_DEMO_MODE:
            raise CommandError("Refusing to seed demo data while FLOWPILOT_DEMO_MODE is off.")
        counts = reset_demo() if options["reset"] else seed_demo()
        self.stdout.write(
            self.style.SUCCESS(f"Demo data ready: {counts['workflows']} workflows, {counts['executions']} executions.")
        )
        self.stdout.write(
            "Demo login: username 'demo', password from FLOWPILOT_DEMO_USER_PASSWORD (default 'flowpilot-demo')."
        )
