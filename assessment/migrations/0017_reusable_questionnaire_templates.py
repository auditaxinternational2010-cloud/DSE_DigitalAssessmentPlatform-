from django.db import migrations, models
import django.db.models.deletion


def create_templates_and_attach(apps, schema_editor):
    Cycle = apps.get_model('assessment', 'AwardCycle')
    Template = apps.get_model('assessment', 'QuestionnaireTemplate')
    Category = apps.get_model('assessment', 'AssessmentCategory')
    Questionnaire = apps.get_model('assessment', 'Questionnaire')
    for cycle in Cycle.objects.all():
        profiles = Category.objects.filter(cycle_id=cycle.pk).values_list('assessment_profile', flat=True).distinct()
        for profile in profiles:
            profile = profile or 'default'
            template, _ = Template.objects.get_or_create(
                cycle_id=cycle.pk, code=profile,
                defaults={'name': profile.replace('_', ' ').title(), 'assessment_profile': profile, 'is_active': True},
            )
            Category.objects.filter(cycle_id=cycle.pk, assessment_profile=profile).update(template_id=template.pk)
        for questionnaire in Questionnaire.objects.filter(cycle_id=cycle.pk):
            profile = getattr(questionnaire.organization, 'assessment_profile', '') or 'default'
            template = Template.objects.filter(cycle_id=cycle.pk, assessment_profile=profile).first()
            if template:
                Questionnaire.objects.filter(pk=questionnaire.pk).update(template_id=template.pk)


class Migration(migrations.Migration):
    atomic = False
    dependencies = [
        ('assessment', '0016_dse_workbook_format'),
        ('accounts', '0014_assessment_profile'),
    ]
    operations = [
        migrations.CreateModel(
            name='QuestionnaireTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('code', models.CharField(blank=True, max_length=50)),
                ('assessment_profile', models.CharField(blank=True, max_length=30)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('cycle', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='templates', to='assessment.awardcycle')),
            ],
            options={'ordering': ['cycle__year', 'name']},
        ),
        migrations.AddConstraint(
            model_name='questionnairetemplate',
            constraint=models.UniqueConstraint(condition=~models.Q(code=''), fields=('cycle', 'code'), name='uniq_template_cycle_code'),
        ),
        migrations.AddField(
            model_name='assessmentcategory', name='template',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='categories', to='assessment.questionnairetemplate'),
        ),
        migrations.AddField(
            model_name='questionnaire', name='template',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='questionnaires', to='assessment.questionnairetemplate'),
        ),
        migrations.RunPython(create_templates_and_attach, migrations.RunPython.noop),
    ]
