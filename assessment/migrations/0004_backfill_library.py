from django.db import migrations


def forwards(apps, schema_editor):
    from assessment.migrations._backfill import backfill_library
    backfill_library(
        apps.get_model('assessment', 'LibraryDocument'),
        apps.get_model('assessment', 'DocumentVersion'),
        apps.get_model('assessment', 'EvidenceLink'),
        apps.get_model('assessment', 'EvidenceUpload'),
    )


def backwards(apps, schema_editor):
    # EvidenceUpload rows are untouched; just clear the library tables.
    apps.get_model('assessment', 'EvidenceLink').objects.all().delete()
    apps.get_model('assessment', 'DocumentVersion').objects.all().delete()
    apps.get_model('assessment', 'LibraryDocument').objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [('assessment', '0003_library_models')]
    operations = [migrations.RunPython(forwards, backwards)]
