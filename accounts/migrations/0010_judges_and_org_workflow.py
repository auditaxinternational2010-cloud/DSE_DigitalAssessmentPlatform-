from django.db import migrations, models


def migrate_legacy_judges(apps, schema_editor):
    UserProfile = apps.get_model('accounts', 'UserProfile')
    UserProfile.objects.filter(role='judge').update(role='judges')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_alter_userprofile_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='requires_judging',
            field=models.BooleanField(
                default=False,
                help_text='If enabled, this organization follows Member → Verifier → Judges → Final Results.',
            ),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='role',
            field=models.CharField(
                choices=[
                    ('admin', 'Admin'),
                    ('member', 'Member'),
                    ('verifier', 'Verifier'),
                    ('judges', 'Judges'),
                ],
                max_length=20,
            ),
        ),
        migrations.RunPython(migrate_legacy_judges, migrations.RunPython.noop),
    ]
