# Generated by Django 4.1.13 on 2025-06-17 18:36

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('database', '0054_transferserviceconfiguration_handler_function'),
    ]

    operations = [
        migrations.AlterField(
            model_name='companyfieldmapping',
            name='service',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='company_field_mappings', to='database.transferserviceconfiguration'),
        ),
    ]
