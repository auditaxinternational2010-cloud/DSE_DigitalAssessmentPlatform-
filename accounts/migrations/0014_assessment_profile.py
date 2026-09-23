from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0013_alter_organization_requires_judging'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='assessment_profile',
            field=models.CharField(
                blank=True,
                choices=[
                    ('bond_issuer', 'Bond Issuer'),
                    ('bond_trader', 'Bond Trader'),
                    ('custodian', 'Custodian'),
                    ('egm', 'EGM'),
                    ('mims', 'MIMs'),
                    ('nomads', 'NOMADs'),
                    ('ldms', 'LDMs'),
                ],
                help_text='DSE assessment workbook profile used for this organisation.',
                max_length=30,
            ),
        ),
    ]
