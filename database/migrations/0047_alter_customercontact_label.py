# Generated by Django 4.1.13 on 2025-06-14 16:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('database', '0046_customercontact_is_active_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customercontact',
            name='label',
            field=models.CharField(choices=[('main', 'Birincil'), ('dask', 'DASK'), ('transfer', 'Transfer'), ('other', 'Diğer')], default='other', help_text='Etiket kullanıcı tarafından seçilemez. İlk kayıt main, diğerleri other/servis otomatik.', max_length=20),
        ),
    ]
