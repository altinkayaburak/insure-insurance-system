# Generated by Django 4.1.13 on 2025-06-17 17:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('database', '0052_transferserviceconfiguration'),
    ]

    operations = [
        migrations.AddField(
            model_name='transferserviceconfiguration',
            name='date_format',
            field=models.CharField(default='%%d.%%m.%%Y', help_text='Servise gönderilecek tarih formatı', max_length=20),
        ),
    ]
