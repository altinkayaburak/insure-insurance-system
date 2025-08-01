# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class Products(models.Model):
    company_code = models.CharField(max_length=50, db_collation='Turkish_CI_AS', blank=True, null=True)
    urun_kod = models.CharField(max_length=50, db_collation='Turkish_CI_AS', blank=True, null=True)
    urun_adi = models.CharField(max_length=100, db_collation='Turkish_CI_AS', blank=True, null=True)
    anabrans_id = models.IntegerField(blank=True, null=True)
    altbrans_id = models.IntegerField(blank=True, null=True)
    sirket_kod = models.CharField(max_length=50, db_collation='Turkish_CI_AS', blank=True, null=True)
    sirket_adi = models.CharField(max_length=100, db_collation='Turkish_CI_AS', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'Products'


class Agency(models.Model):
    id = models.BigAutoField()
    name = models.CharField(unique=True, max_length=255, db_collation='Turkish_CI_AS')
    domain = models.CharField(unique=True, max_length=255, db_collation='Turkish_CI_AS', blank=True, null=True)
    is_active = models.BooleanField()
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'agency'


class Agencybranch(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255, db_collation='Turkish_CI_AS')
    is_main = models.BooleanField()
    branch_type = models.CharField(max_length=10, db_collation='Turkish_CI_AS')
    agency_id = models.BigIntegerField()

    class Meta:
        managed = False
        db_table = 'agencybranch'


class Agencycompany(models.Model):
    agency_id = models.IntegerField()
    company_id = models.IntegerField()
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'agencycompany'


class Agencypasswords(models.Model):
    agency_id = models.IntegerField()
    insurance_company_id = models.IntegerField()
    username = models.CharField(max_length=255, db_collation='Turkish_CI_AS', blank=True, null=True)
    password = models.CharField(max_length=255, db_collation='Turkish_CI_AS', blank=True, null=True)
    partaj_code = models.CharField(max_length=255, db_collation='Turkish_CI_AS', blank=True, null=True)
    web_username = models.CharField(max_length=255, db_collation='Turkish_CI_AS', blank=True, null=True)
    web_password = models.CharField(max_length=255, db_collation='Turkish_CI_AS', blank=True, null=True)
    cookie = models.TextField(db_collation='Turkish_CI_AS', blank=True, null=True)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'agencypasswords'


class AuthGroup(models.Model):
    name = models.CharField(unique=True, max_length=150, db_collation='Turkish_CI_AS')

    class Meta:
        managed = False
        db_table = 'auth_group'


class AuthGroupPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)
    permission = models.ForeignKey('AuthPermission', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_group_permissions'
        unique_together = (('group', 'permission'),)


class AuthPermission(models.Model):
    name = models.CharField(max_length=255, db_collation='Turkish_CI_AS')
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING)
    codename = models.CharField(max_length=100, db_collation='Turkish_CI_AS')

    class Meta:
        managed = False
        db_table = 'auth_permission'
        unique_together = (('content_type', 'codename'),)


class AuthUser(models.Model):
    password = models.CharField(max_length=128, db_collation='Turkish_CI_AS')
    last_login = models.DateTimeField(blank=True, null=True)
    is_superuser = models.BooleanField()
    username = models.CharField(unique=True, max_length=150, db_collation='Turkish_CI_AS')
    first_name = models.CharField(max_length=150, db_collation='Turkish_CI_AS')
    last_name = models.CharField(max_length=150, db_collation='Turkish_CI_AS')
    email = models.CharField(max_length=254, db_collation='Turkish_CI_AS')
    is_staff = models.BooleanField()
    is_active = models.BooleanField()
    date_joined = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'auth_user'


class AuthUserGroups(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_user_groups'
        unique_together = (('user', 'group'),)


class AuthUserUserPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)
    permission = models.ForeignKey(AuthPermission, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_user_user_permissions'
        unique_together = (('user', 'permission'),)


class DjangoAdminLog(models.Model):
    action_time = models.DateTimeField()
    object_id = models.TextField(db_collation='Turkish_CI_AS', blank=True, null=True)
    object_repr = models.CharField(max_length=200, db_collation='Turkish_CI_AS')
    action_flag = models.SmallIntegerField()
    change_message = models.TextField(db_collation='Turkish_CI_AS')
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING, blank=True, null=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'django_admin_log'


class DjangoContentType(models.Model):
    app_label = models.CharField(max_length=100, db_collation='Turkish_CI_AS')
    model = models.CharField(max_length=100, db_collation='Turkish_CI_AS')

    class Meta:
        managed = False
        db_table = 'django_content_type'
        unique_together = (('app_label', 'model'),)


class DjangoMigrations(models.Model):
    id = models.BigAutoField(primary_key=True)
    app = models.CharField(max_length=255, db_collation='Turkish_CI_AS')
    name = models.CharField(max_length=255, db_collation='Turkish_CI_AS')
    applied = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_migrations'


class DjangoSession(models.Model):
    session_key = models.CharField(primary_key=True, max_length=40, db_collation='Turkish_CI_AS')
    session_data = models.TextField(db_collation='Turkish_CI_AS')
    expire_date = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_session'


class Insurancecompany(models.Model):
    name = models.CharField(max_length=255, db_collation='Turkish_CI_AS')
    company_code = models.CharField(unique=True, max_length=100, db_collation='Turkish_CI_AS')
    is_active = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'insurancecompany'


class Keyparameters(models.Model):
    keyparameterid = models.AutoField(db_column='KeyParameterID', primary_key=True)  # Field name made lowercase.
    createddate = models.DateTimeField(db_column='CreatedDate')  # Field name made lowercase.
    keyid = models.ForeignKey('Keys', models.DO_NOTHING, db_column='KeyID')  # Field name made lowercase.
    parameterid = models.ForeignKey('Parameters', models.DO_NOTHING, db_column='ParameterID')  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'keyparameters'
        unique_together = (('keyid', 'parameterid'),)


class Keys(models.Model):
    keyid = models.AutoField(db_column='KeyID', primary_key=True)  # Field name made lowercase.
    keyname = models.CharField(db_column='KeyName', max_length=255, db_collation='Turkish_CI_AS')  # Field name made lowercase.
    description = models.TextField(db_column='Description', db_collation='Turkish_CI_AS', blank=True, null=True)  # Field name made lowercase.
    createddate = models.DateTimeField(db_column='CreatedDate')  # Field name made lowercase.
    updateddate = models.DateTimeField(db_column='UpdatedDate', blank=True, null=True)  # Field name made lowercase.
    deleteddate = models.DateTimeField(db_column='DeletedDate', blank=True, null=True)  # Field name made lowercase.
    isactive = models.BooleanField(db_column='IsActive')  # Field name made lowercase.
    inputtype = models.CharField(db_column='InputType', max_length=50, db_collation='Turkish_CI_AS', blank=True, null=True)  # Field name made lowercase.
    minlength = models.IntegerField(db_column='MinLength', blank=True, null=True)  # Field name made lowercase.
    maxlength = models.IntegerField(db_column='MaxLength', blank=True, null=True)  # Field name made lowercase.
    regexpattern = models.CharField(db_column='RegexPattern', max_length=255, db_collation='Turkish_CI_AS', blank=True, null=True)  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'keys'


class Parameters(models.Model):
    parameterid = models.AutoField(db_column='ParameterID', primary_key=True)  # Field name made lowercase.
    parametername = models.CharField(db_column='ParameterName', max_length=100, db_collation='Turkish_CI_AS')  # Field name made lowercase.
    defaultvalue = models.CharField(db_column='DefaultValue', max_length=255, db_collation='Turkish_CI_AS', blank=True, null=True)  # Field name made lowercase.
    createddate = models.DateTimeField(db_column='CreatedDate')  # Field name made lowercase.
    updateddate = models.DateTimeField(db_column='UpdatedDate', blank=True, null=True)  # Field name made lowercase.
    isactive = models.BooleanField(db_column='IsActive')  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'parameters'
