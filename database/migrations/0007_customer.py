# Generated by Django 4.1.13 on 2025-04-01 06:54

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('database', '0006_city'),
    ]

    operations = [
        migrations.CreateModel(
            name='Customer',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('customer_key', models.CharField(db_column='customer_key', max_length=30, unique=True, editable=False)),
                ('agency_id', models.IntegerField(db_column='agency_id')),
                ('user_id', models.IntegerField(blank=True, db_column='user_id', null=True)),
                ('identity_number', models.CharField(db_column='identity_number', max_length=11, unique=True)),
                ('birth_date', models.DateField(blank=True, db_column='birth_date', null=True)),
                ('full_name', models.CharField(blank=True, db_column='full_name', max_length=255, null=True)),
                ('birth_place', models.CharField(blank=True, db_column='birth_place', max_length=100, null=True)),
                ('gender', models.CharField(blank=True, db_column='gender', max_length=10, null=True)),
                ('image_url', models.URLField(blank=True, db_column='image_url', null=True)),
                ('marital_status', models.CharField(blank=True, db_column='marital_status', max_length=50, null=True)),
                ('type', models.CharField(blank=True, db_column='type', max_length=10, null=True)),
                ('deceased', models.BooleanField(blank=True, db_column='deceased', null=True)),
                ('nationality_code', models.CharField(blank=True, db_column='nationality_code', max_length=10, null=True)),
                ('father_name', models.CharField(blank=True, db_column='father_name', max_length=100, null=True)),
                ('mother_name', models.CharField(blank=True, db_column='mother_name', max_length=100, null=True)),
                ('app_user_id', models.IntegerField(blank=True, db_column='app_user_id', null=True)),
                ('phone_number', models.CharField(blank=True, db_column='phone_number', max_length=20, null=True)),
                ('address_code', models.CharField(blank=True, db_column='address_code', max_length=50, null=True)),
                ('city_code', models.CharField(blank=True, db_column='city_code', max_length=50, null=True)),
                ('state_code', models.CharField(blank=True, db_column='state_code', max_length=50, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_column='created_at')),
                ('updated_at', models.DateTimeField(auto_now=True, db_column='updated_at')),
            ],
            options={
                'verbose_name': 'Customer',
                'verbose_name_plural': 'Customers',
                'db_table': 'customers',
            },
        ),
    ]
