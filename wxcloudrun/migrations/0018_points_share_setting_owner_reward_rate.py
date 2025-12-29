from datetime import datetime

from django.db import migrations, models


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
    dependencies = [
        ('wxcloudrun', '0017_contact_setting'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pointssharesetting',
            name='merchant_rate',
            field=models.PositiveIntegerField(default=5, verbose_name='业主奖励比例(%)'),
        ),
        migrations.RunPython(set_default_owner_reward_rate, migrations.RunPython.noop),
    ]

