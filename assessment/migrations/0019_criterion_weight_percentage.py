from decimal import Decimal

from django.db import migrations, models
from django.core.validators import MinValueValidator, MaxValueValidator


def convert_fraction_weights_to_percentages(apps, schema_editor):
    Criterion = apps.get_model('assessment', 'Criterion')
    for criterion in Criterion.objects.filter(weight__gt=0, weight__lte=1).iterator():
        criterion.weight = criterion.weight * Decimal('100')
        criterion.save(update_fields=['weight'])


def reverse_percentage_weights(apps, schema_editor):
    Criterion = apps.get_model('assessment', 'Criterion')
    for criterion in Criterion.objects.filter(weight__gt=1).iterator():
        criterion.weight = criterion.weight / Decimal('100')
        criterion.save(update_fields=['weight'])


class Migration(migrations.Migration):

    dependencies = [
        ('assessment', '0018_fix_questionnairetemplate_updated_at'),
    ]

    operations = [
        migrations.RunPython(
            convert_fraction_weights_to_percentages,
            reverse_percentage_weights,
        ),
        migrations.AlterField(
            model_name='criterion',
            name='weight',
            field=models.DecimalField(
                decimal_places=6,
                default=0,
                help_text='Percentage weight (0–100). Example: 25 means 25%.',
                max_digits=10,
                validators=[MinValueValidator(0), MaxValueValidator(100)],
            ),
        ),
    ]
