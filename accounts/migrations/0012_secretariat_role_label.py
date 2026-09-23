from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0011_alter_userprofile_role'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='role',
            field=models.CharField(
                choices=[
                    ('admin', 'Admin'),
                    ('member', 'Member'),
                    ('verifier', 'Secretariat'),
                    ('judge', 'Judge'),
                ],
                max_length=20,
            ),
        ),
    ]
