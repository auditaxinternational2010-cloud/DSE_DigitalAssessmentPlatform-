from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0014_assessment_profile'),
        ('assessment', '0019_criterion_weight_percentage'),
    ]

    operations = [
        migrations.AddField(
            model_name='participationrequest',
            name='requested_questionnaires',
            field=models.ManyToManyField(
                blank=False,
                help_text='Questionnaire templates requested during registration.',
                related_name='participation_requests',
                to='assessment.questionnairetemplate',
            ),
        ),
    ]
