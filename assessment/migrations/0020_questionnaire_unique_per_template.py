from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('assessment', '0019_criterion_weight_percentage'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='questionnaire',
            unique_together={('cycle', 'organization', 'template')},
        ),
    ]
