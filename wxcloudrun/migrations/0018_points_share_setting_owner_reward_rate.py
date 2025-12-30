from datetime import datetime

from django.db import migrations, models


def ensure_points_share_setting_table(apps, schema_editor):
    """
    兼容历史迁移：0010 使用 SeparateDatabaseAndState 仅标记 PointsShareSetting 已存在，
    但在新环境中该表可能并未真实创建，导致后续迁移失败。
    """
    PointsShareSetting = apps.get_model('wxcloudrun', 'PointsShareSetting')
    table_name = PointsShareSetting._meta.db_table
    existing_tables = {t.lower() for t in schema_editor.connection.introspection.table_names()}
    if table_name.lower() not in existing_tables:
        schema_editor.create_model(PointsShareSetting)


def set_default_owner_reward_rate(apps, schema_editor):
    PointsShareSetting = apps.get_model('wxcloudrun', 'PointsShareSetting')
    now = datetime.now()
    obj, created = PointsShareSetting.objects.get_or_create(
        id=1,
        defaults={'merchant_rate': 5, 'created_at': now, 'updated_at': now},
    )
    if not created and obj.merchant_rate != 5:
        PointsShareSetting.objects.filter(id=obj.id).update(merchant_rate=5, updated_at=now)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('wxcloudrun', '0017_contact_setting'),
    ]

    operations = [
        migrations.RunPython(ensure_points_share_setting_table, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='pointssharesetting',
            name='merchant_rate',
            field=models.PositiveIntegerField(default=5, verbose_name='业主奖励比例(%)'),
        ),
        migrations.RunPython(set_default_owner_reward_rate, migrations.RunPython.noop),
    ]
