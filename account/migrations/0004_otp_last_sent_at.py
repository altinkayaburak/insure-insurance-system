# Generated by Django 4.1.13 on 2025-04-04 19:56

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0003_remove_otp_updated_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='otp',
            name='last_sent_at',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
