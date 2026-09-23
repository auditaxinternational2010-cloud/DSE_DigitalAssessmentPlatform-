import django.db.models.deletion
import assessment.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assessment', '0005_remove_evidenceupload'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Clear unique_together referencing document_version BEFORE removing the field
        migrations.AlterUniqueTogether(
            name='evidencelink',
            unique_together=set(),
        ),
        # 2. Remove the FK from EvidenceLink to DocumentVersion (drops column + constraint)
        migrations.RemoveField(
            model_name='evidencelink',
            name='document_version',
        ),
        # 3. Drop DocumentVersion (EvidenceLink no longer references it)
        migrations.DeleteModel(name='DocumentVersion'),
        # 4. Drop LibraryDocument (DocumentVersion is gone)
        migrations.DeleteModel(name='LibraryDocument'),
        # 5. Create EvidenceDocument
        migrations.CreateModel(
            name='EvidenceDocument',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('file', models.FileField(upload_to=assessment.models.evidence_upload_path)),
                ('file_size', models.PositiveIntegerField(default=0)),
                ('original_filename', models.CharField(max_length=255)),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('organization', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='evidence_documents',
                    to='accounts.organization',
                )),
                ('uploaded_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='uploaded_evidence',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-uploaded_at']},
        ),
        # 6. Add nullable document FK to EvidenceLink
        migrations.AddField(
            model_name='evidencelink',
            name='document',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='evidence_links',
                to='assessment.evidencedocument',
            ),
        ),
        # 7. Clear orphaned EvidenceLink rows (had document_version, now NULL document)
        migrations.RunSQL(
            'DELETE FROM assessment_evidencelink;',
            migrations.RunSQL.noop,
        ),
        # 8. Make document non-nullable
        migrations.AlterField(
            model_name='evidencelink',
            name='document',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='evidence_links',
                to='assessment.evidencedocument',
            ),
        ),
        # 9. Restore unique_together with new FK
        migrations.AlterUniqueTogether(
            name='evidencelink',
            unique_together={('response', 'document')},
        ),
    ]
