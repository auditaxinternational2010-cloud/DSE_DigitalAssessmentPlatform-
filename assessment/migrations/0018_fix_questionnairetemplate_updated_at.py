from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ("assessment", "0017_reusable_questionnaire_templates"),
    ]

    operations = [
        migrations.AddField(
            model_name="questionnairetemplate",
            name="updated_at",
            field=models.DateTimeField(
                auto_now=True,
                default=timezone.now,
            ),
            preserve_default=False,
        ),
    ]