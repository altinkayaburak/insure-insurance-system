# Generated by Django 4.1.13 on 2025-06-06 17:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('database', '0034_customer_address_text'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customer',
            name='deceased',
            field=models.DateField(blank=True, db_column='deceased', null=True),
        ),
    ]
