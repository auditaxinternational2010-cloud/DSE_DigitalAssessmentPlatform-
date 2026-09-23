"""
Find (and optionally delete) evidence files in storage that no EvidenceDocument
row references.

Orphans come from two places:
  * historical test runs that wrote to real storage (DEFAULT_FILE_STORAGE was
    removed in Django 5.1, so per-test override_settings of it was a silent
    no-op — see the TESTING guard in settings.py), and
  * any upload whose row failed to commit after the file was already written.

SAFETY: this command decides what to delete by diffing storage against the
database, so pointing it at the wrong database would classify every real file
as an orphan. Several guards below exist specifically to make that mistake
loud instead of catastrophic. It is read-only unless --delete is passed.
"""

from datetime import datetime, timedelta, timezone as _dt_timezone

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from assessment.models import EvidenceDocument

# S3 accepts at most 1000 keys per delete_objects call.
_S3_DELETE_BATCH = 1000


class Command(BaseCommand):
    help = (
        'Report evidence files in storage with no EvidenceDocument row. '
        'Read-only by default; pass --delete to actually remove them.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--prefix', default='evidence/',
            help='Storage key prefix to scan (default: evidence/). Keeps the '
                 'scan away from cycles/ Excel uploads and anything else.',
        )
        parser.add_argument(
            '--delete', action='store_true',
            help='Actually delete. Without this the command only reports.',
        )
        parser.add_argument(
            '--min-age-hours', type=int, default=24,
            help='Ignore objects newer than this (default: 24). Protects an '
                 'in-flight upload whose row has not committed yet.',
        )
        parser.add_argument(
            '--max-orphan-pct', type=float, default=25.0,
            help='Abort if orphans exceed this share of scanned objects '
                 '(default: 25). A high ratio usually means the wrong database.',
        )
        parser.add_argument(
            '--force', action='store_true',
            help='Override the --max-orphan-pct guard. Think first.',
        )
        parser.add_argument(
            '--noinput', '--no-input', action='store_true', dest='noinput',
            help='Skip the interactive confirmation (for non-tty runs).',
        )
        parser.add_argument(
            '--limit', type=int, default=50,
            help='Max orphan keys to print (default: 50; 0 for all).',
        )

    # ── storage adapters ─────────────────────────────────────────────────────

    def _iter_objects(self, storage, prefix):
        """Yield (key, size, last_modified_aware) for everything under prefix."""
        if hasattr(storage, 'bucket'):          # S3Boto3Storage
            for obj in storage.bucket.objects.filter(Prefix=prefix):
                yield obj.key, obj.size, obj.last_modified
            return

        # FileSystemStorage — walk the tree under MEDIA_ROOT/<prefix>.
        import os
        root = os.path.join(settings.MEDIA_ROOT, prefix)
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, settings.MEDIA_ROOT).replace(os.sep, '/')
                st = os.stat(full)
                mtime = datetime.fromtimestamp(st.st_mtime, tz=_dt_timezone.utc)
                yield rel, st.st_size, mtime

    def _delete_keys(self, storage, keys):
        """Delete keys, batching on S3. Returns the number removed."""
        if hasattr(storage, 'bucket'):
            removed = 0
            for i in range(0, len(keys), _S3_DELETE_BATCH):
                batch = keys[i:i + _S3_DELETE_BATCH]
                resp = storage.bucket.delete_objects(
                    Delete={'Objects': [{'Key': k} for k in batch], 'Quiet': True}
                )
                for err in resp.get('Errors', []):
                    self.stderr.write(self.style.ERROR(
                        f"  failed: {err.get('Key')} — {err.get('Message')}"))
                removed += len(batch) - len(resp.get('Errors', []))
            return removed

        removed = 0
        for k in keys:
            storage.delete(k)
            removed += 1
        return removed

    # ── main ─────────────────────────────────────────────────────────────────

    def handle(self, *args, **opts):
        storage = default_storage
        prefix = opts['prefix']
        is_s3 = hasattr(storage, 'bucket')
        target = (f'S3 bucket "{storage.bucket_name}" (region '
                  f'{settings.AWS_S3_REGION_NAME or "default"})'
                  if is_s3 else f'local filesystem {settings.MEDIA_ROOT}')

        self.stdout.write(f'Storage  : {target}')
        self.stdout.write(f'Database : {connection.settings_dict.get("NAME")} '
                          f'on {connection.settings_dict.get("HOST") or "local"}')
        self.stdout.write(f'Prefix   : {prefix}')

        # Guard 1: an empty table would mark every single file an orphan. This
        # is the wrong-database failure mode, and it is unrecoverable.
        referenced = set(
            EvidenceDocument.objects
            .exclude(file='').exclude(file__isnull=True)
            .values_list('file', flat=True)
        )
        if not referenced:
            raise CommandError(
                'No EvidenceDocument rows reference a file in this database. '
                'Refusing to run — every object would look orphaned. Check '
                'that you are pointed at the right database.'
            )
        self.stdout.write(f'Rows     : {len(referenced)} documents reference a file\n')

        cutoff = timezone.now() - timedelta(hours=opts['min_age_hours'])
        orphans, orphan_bytes = [], 0
        scanned = skipped_new = 0

        for key, size, modified in self._iter_objects(storage, prefix):
            scanned += 1
            if key in referenced:
                continue
            if modified and modified > cutoff:
                skipped_new += 1
                continue
            orphans.append(key)
            orphan_bytes += size

        self.stdout.write(f'Scanned  : {scanned} objects under "{prefix}"')
        if skipped_new:
            self.stdout.write(
                f'Skipped  : {skipped_new} unreferenced but newer than '
                f'{opts["min_age_hours"]}h (possibly still uploading)')

        if not orphans:
            self.stdout.write(self.style.SUCCESS('No orphans. Nothing to do.'))
            return

        mb = orphan_bytes / (1024 * 1024)
        pct = (len(orphans) / scanned * 100) if scanned else 0
        self.stdout.write(self.style.WARNING(
            f'Orphans  : {len(orphans)} objects, {orphan_bytes} bytes '
            f'({mb:.2f} MB) — {pct:.1f}% of scanned'))

        shown = orphans if opts['limit'] == 0 else orphans[:opts['limit']]
        for k in shown:
            self.stdout.write(f'  {k}')
        if len(shown) < len(orphans):
            self.stdout.write(f'  ... and {len(orphans) - len(shown)} more')

        if not opts['delete']:
            self.stdout.write(self.style.SUCCESS(
                '\nDRY RUN — nothing deleted. Re-run with --delete to remove these.'))
            return

        # Guard 2: a high orphan ratio is the signature of a mismatched
        # database, not of accumulated junk.
        if pct > opts['max_orphan_pct'] and not opts['force']:
            raise CommandError(
                f'{pct:.1f}% of scanned objects look orphaned, above the '
                f'{opts["max_orphan_pct"]}% threshold. This usually means the '
                f'database does not match the storage. Refusing to delete. '
                f'Pass --force only if you are certain.'
            )

        # Guard 3: make the human name the target before anything is destroyed.
        if not opts['noinput']:
            expect = storage.bucket_name if is_s3 else 'LOCAL'
            self.stdout.write(self.style.WARNING(
                f'\nAbout to permanently delete {len(orphans)} objects from {target}.'))
            try:
                typed = input(f'Type "{expect}" to confirm: ').strip()
            except EOFError:
                raise CommandError(
                    'No interactive input available. Re-run with --noinput if '
                    'you are sure (and you have reviewed the dry run first).')
            if typed != expect:
                raise CommandError('Confirmation did not match. Aborted.')

        removed = self._delete_keys(storage, orphans)
        self.stdout.write(self.style.SUCCESS(
            f'Deleted {removed} of {len(orphans)} orphaned objects '
            f'({mb:.2f} MB reclaimed).'))
