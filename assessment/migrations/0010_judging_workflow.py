from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assessment', '0009_assessmentcategory_is_informal_sector_only'),
    ]

    operations = [
        migrations.AddField(
            model_name='questionnaire',
            name='judging_completed',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='questionnaire',
            name='judged_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='questionnaire',
            name='judged_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name='judged_questionnaires',
                to='auth.user',
            ),
        ),
    ]
