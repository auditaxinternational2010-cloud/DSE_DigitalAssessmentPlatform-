from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('assessment', '0011_questionnaire_judging_comments'),
    ]

    operations = [
        migrations.CreateModel(
            name='JudgeResponse',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('score', models.PositiveIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(5)])),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('criterion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='judge_responses', to='assessment.criterion')),
                ('judge', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='judge_responses', to='auth.user')),
                ('questionnaire', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='judge_responses', to='assessment.questionnaire')),
            ],
            options={
                'ordering': ['criterion__category__order', 'criterion__order'],
                'unique_together': {('questionnaire', 'judge', 'criterion')},
            },
        ),
        migrations.AddIndex(
            model_name='judgeresponse',
            index=models.Index(fields=['questionnaire', 'criterion'], name='assessment_judge_questio_8c1f1f_idx'),
        ),
        migrations.AddIndex(
            model_name='judgeresponse',
            index=models.Index(fields=['judge', 'questionnaire'], name='assessment_judge_judge_id_1e9f5a_idx'),
        ),
    ]
