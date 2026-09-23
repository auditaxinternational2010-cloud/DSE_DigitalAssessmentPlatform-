from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('assessment', '0012_judge_responses'),
    ]

    operations = [
        migrations.CreateModel(
            name='StageSubmission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stage', models.CharField(choices=[('secretariat', 'Secretariat'), ('judge', 'Judge')], max_length=20)),
                ('submitted_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('category', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='stage_submissions', to='assessment.assessmentcategory')),
                ('questionnaire', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stage_submissions', to='assessment.questionnaire')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stage_submissions', to='auth.user')),
            ],
            options={
                'ordering': ['stage', 'category__order', 'updated_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='stagesubmission',
            constraint=models.UniqueConstraint(fields=('questionnaire', 'user', 'stage', 'category'), name='uniq_stage_submission_with_category'),
        ),
        migrations.AddConstraint(
            model_name='stagesubmission',
            constraint=models.UniqueConstraint(condition=models.Q(('category__isnull', True)), fields=('questionnaire', 'user', 'stage'), name='uniq_stage_submission_without_category'),
        ),
    ]
