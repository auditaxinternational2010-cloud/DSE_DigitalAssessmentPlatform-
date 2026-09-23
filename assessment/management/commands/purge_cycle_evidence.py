from django.core.management.base import BaseCommand, CommandError

from assessment.models import AwardCycle


class Command(BaseCommand):
    help = 'Legacy command — EvidenceUpload has been removed. No-op.'

    def add_arguments(self, parser):
        parser.add_argument('cycle_id', type=int, help='Primary key of the AwardCycle.')
        parser.add_argument(
            '--dry-run', action='store_true',
            help='No-op (kept for backwards-compatible invocations).',
        )

    def handle(self, *args, **options):
        try:
            cycle = AwardCycle.objects.get(pk=options['cycle_id'])
        except AwardCycle.DoesNotExist:
            raise CommandError(f"No AwardCycle with pk={options['cycle_id']}")

        if options['dry_run']:
            self.stdout.write(f'DRY RUN: EvidenceUpload has been removed; nothing to purge for cycle "{cycle.name}".')
            return

        self.stdout.write(self.style.SUCCESS(f'Done. EvidenceUpload has been removed; nothing to purge for cycle "{cycle.name}".'))
