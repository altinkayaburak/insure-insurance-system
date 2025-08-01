# Generated by Django 4.1.13 on 2025-03-31 13:52

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('database', '0005_key_visibleifkey_key_visibleifvalue_and_more'),
        ('agency', '0002_agencyserviceauthorization'),
        ('gateway', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='proposalservicelog',
            options={},
        ),
        migrations.RemoveField(
            model_name='proposalservicelog',
            name='agency_id',
        ),
        migrations.RemoveField(
            model_name='proposalservicelog',
            name='service_id',
        ),
        migrations.RemoveField(
            model_name='proposalservicelog',
            name='user_id',
        ),
        migrations.AddField(
            model_name='proposalservicelog',
            name='agency',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='agency.agency'),
        ),
        migrations.AddField(
            model_name='proposalservicelog',
            name='service',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='database.serviceconfiguration'),
        ),
        migrations.AddField(
            model_name='proposalservicelog',
            name='user',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='proposalservicelog',
            name='product_code',
            field=models.CharField(max_length=100),
        ),
        migrations.AlterField(
            model_name='proposalservicelog',
            name='proposal_id',
            field=models.PositiveIntegerField(),
        ),
    ]
