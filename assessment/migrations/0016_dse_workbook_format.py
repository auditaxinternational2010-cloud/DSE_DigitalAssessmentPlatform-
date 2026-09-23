from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('assessment', '0015_rename_assessment_judge_questio_8c1f1f_idx_assessment__questio_dae775_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='assessmentcategory',
            name='code',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name='assessmentcategory',
            name='weight',
            field=models.DecimalField(decimal_places=6, default=0, max_digits=8),
        ),
        migrations.AddField(
            model_name='assessmentcategory',
            name='assessment_profile',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AlterField(
            model_name='criterion',
            name='number',
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name='criterion',
            name='name',
            field=models.CharField(max_length=1000),
        ),
        migrations.AddField(
            model_name='criterion',
            name='area_code',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='criterion',
            name='assessment_area',
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name='criterion',
            name='assessment_criterion_code',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='criterion',
            name='assessment_criterion',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='criterion',
            name='regulation',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='criterion',
            name='weight',
            field=models.DecimalField(decimal_places=8, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='response',
            name='response',
            field=models.TextField(blank=True, default=''),
        ),
    ]
