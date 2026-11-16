from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [
        ('assessment', '0020_questionnaire_unique_per_template'),
    ]

    operations = [
        migrations.AlterField(
            model_name='judgeresponse',
            name='score',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=12,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(0),
                ],
                help_text='Numeric judge score greater than the criterion weight, with up to two decimal places.',
            ),
        ),
    ]
