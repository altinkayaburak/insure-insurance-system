# Generated by Django 4.1.13 on 2025-06-24 13:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('database', '0067_assetcars_is_verified'),
    ]

    operations = [
        migrations.AlterField(
            model_name='assetcars',
            name='AracRenk',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
    ]
