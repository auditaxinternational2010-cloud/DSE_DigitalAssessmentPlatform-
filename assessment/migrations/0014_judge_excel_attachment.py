from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assessment', '0013_stage_submission'),
    ]

    operations = [
        migrations.AddField(
            model_name='judgeresponse',
            name='excel_attachment',
            field=models.FileField(
                blank=True,
                help_text='Optional Excel attachment for this criterion (.xlsx or .xls).',
                null=True,
                upload_to='judge_attachments/',
            ),
        ),
    ]
