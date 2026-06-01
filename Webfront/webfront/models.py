from django.db import models


class DataSource(models.Model):
    source_id = models.UUIDField(primary_key=True)
    source_type = models.TextField(blank=True, null=True)
    provider = models.TextField(blank=True, null=True)
    dataset_name = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'data_source'


class UserAccount(models.Model):
    user_id = models.UUIDField(primary_key=True)
    username = models.TextField(unique=True)
    role = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'user_account'


class Airfoil(models.Model):
    airfoil_id = models.UUIDField(primary_key=True)
    airfoil_code = models.TextField(unique=True)
    name = models.TextField()
    category = models.TextField(blank=True, null=True)
    family = models.TextField(blank=True, null=True)
    generation_method = models.TextField(blank=True, null=True)
    is_generated = models.BooleanField(blank=True, null=True)
    remark = models.TextField(blank=True, null=True)
    source = models.ForeignKey(DataSource, models.DO_NOTHING)
    is_deleted = models.BooleanField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'airfoil'


class AirfoilVersion(models.Model):
    version_id = models.UUIDField(primary_key=True)
    airfoil = models.ForeignKey(Airfoil, models.DO_NOTHING)
    version_no = models.IntegerField()
    version_type = models.TextField()
    status = models.TextField()
    is_current = models.BooleanField(blank=True, null=True)
    change_note = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(UserAccount, models.DO_NOTHING, db_column='created_by')
    created_at = models.DateTimeField(blank=True, null=True)
    is_deleted = models.BooleanField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'airfoil_version'


class CoordinatePoint(models.Model):
    point_id = models.UUIDField(primary_key=True)
    version = models.ForeignKey(AirfoilVersion, models.DO_NOTHING)
    surface = models.TextField()
    point_order = models.IntegerField()
    x = models.DecimalField(max_digits=65535, decimal_places=65535)
    y = models.DecimalField(max_digits=65535, decimal_places=65535)
    is_deleted = models.BooleanField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'coordinate_point'


class ExperimentCondition(models.Model):
    condition_id = models.UUIDField(primary_key=True)
    alpha_deg = models.DecimalField(max_digits=65535, decimal_places=65535)
    reynolds_number = models.DecimalField(max_digits=65535, decimal_places=65535)

    class Meta:
        managed = False
        db_table = 'experiment_condition'


class PerformanceRecord(models.Model):
    record_id = models.UUIDField(primary_key=True)
    version = models.ForeignKey(AirfoilVersion, models.DO_NOTHING)
    condition = models.ForeignKey(ExperimentCondition, models.DO_NOTHING)
    cl = models.DecimalField(max_digits=65535, decimal_places=65535)
    cd = models.DecimalField(max_digits=65535, decimal_places=65535)
    l_over_d = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    source_type = models.TextField()
    is_anomaly = models.BooleanField(blank=True, null=True)
    is_deleted = models.BooleanField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'performance_record'


class AnomalyRule(models.Model):
    rule_id = models.UUIDField(primary_key=True)
    rule_code = models.TextField(unique=True)
    description = models.TextField()
    severity = models.TextField()
    is_enabled = models.BooleanField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'anomaly_rule'


class AnomalyRecord(models.Model):
    anomaly_id = models.UUIDField(primary_key=True)
    version = models.ForeignKey(AirfoilVersion, models.DO_NOTHING)
    record = models.ForeignKey(PerformanceRecord, models.DO_NOTHING, blank=True, null=True)
    rule = models.ForeignKey(AnomalyRule, models.DO_NOTHING)
    status = models.TextField()
    details = models.TextField(blank=True, null=True)
    detected_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'anomaly_record'