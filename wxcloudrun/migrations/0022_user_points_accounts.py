from datetime import date, datetime

import django.db.models.deletion
from django.db import migrations, models


POINTS_IDENTITY_CHOICES = (
    ('OWNER', 'OWNER'),
    ('PROPERTY', 'PROPERTY'),
    ('MERCHANT', 'MERCHANT'),
)


def backfill_user_points_accounts(apps, schema_editor):
    """将历史 UserInfo.daily_points/total_points 迁移到「当前 active_identity」对应的独立积分账户。

    说明：
    - 旧版本积分是写在 UserInfo 上的单一余额，无法区分来源身份；
    - 为避免把同一份积分复制到多个身份导致“可重复使用”，迁移时只写入 active_identity 对应账户；
    - 其他身份账户在首次使用/切换时再按需创建（默认为 0）。
    """
    UserInfo = apps.get_model('wxcloudrun', 'UserInfo')
    UserPointsAccount = apps.get_model('wxcloudrun', 'UserPointsAccount')

    db_alias = schema_editor.connection.alias
    today = date.today()
    now = datetime.now()

    allowed = {'OWNER', 'MERCHANT', 'PROPERTY'}

    batch: list = []
    for user in (
        UserInfo.objects.using(db_alias)
        .all()
        .only('id', 'active_identity', 'daily_points', 'total_points', 'daily_points_date')
        .iterator(chunk_size=500)
    ):
        identity = user.active_identity if user.active_identity in allowed else 'OWNER'
        batch.append(
            UserPointsAccount(
                user_id=user.id,
                identity_type=identity,
                daily_points=int(user.daily_points or 0),
                total_points=int(user.total_points or 0),
                daily_points_date=user.daily_points_date or today,
                created_at=now,
                updated_at=now,
            )
        )
        if len(batch) >= 1000:
            UserPointsAccount.objects.using(db_alias).bulk_create(batch, ignore_conflicts=True)
            batch.clear()

    if batch:
        UserPointsAccount.objects.using(db_alias).bulk_create(batch, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ('wxcloudrun', '0021_recommended_merchants'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserPointsAccount',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('identity_type', models.CharField(choices=POINTS_IDENTITY_CHOICES, max_length=20, verbose_name='积分身份')),
                ('daily_points', models.IntegerField(default=0, verbose_name='当日积分')),
                ('total_points', models.IntegerField(default=0, verbose_name='累计积分')),
                ('daily_points_date', models.DateField(blank=True, null=True, verbose_name='当日积分日期')),
                ('created_at', models.DateTimeField(default=datetime.now, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(default=datetime.now, verbose_name='更新时间')),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='points_accounts',
                        to='wxcloudrun.userinfo',
                        verbose_name='关联用户',
                    ),
                ),
            ],
            options={
                'db_table': 'UserPointsAccount',
                'verbose_name': '用户积分账户',
                'verbose_name_plural': '用户积分账户',
                'unique_together': {('user', 'identity_type')},
            },
        ),
        migrations.AddIndex(
            model_name='userpointsaccount',
            index=models.Index(fields=['user', 'identity_type'], name='UserPointsAccount_user_identity_idx'),
        ),
        migrations.AddField(
            model_name='pointsrecord',
            name='identity_type',
            field=models.CharField(choices=POINTS_IDENTITY_CHOICES, default='OWNER', max_length=20, verbose_name='积分身份'),
        ),
        migrations.AddField(
            model_name='pointsrecord',
            name='daily_points',
            field=models.IntegerField(default=0, verbose_name='当日积分'),
        ),
        migrations.AddField(
            model_name='pointsrecord',
            name='total_points',
            field=models.IntegerField(default=0, verbose_name='累计积分'),
        ),
        migrations.AddIndex(
            model_name='pointsrecord',
            index=models.Index(fields=['user', 'identity_type'], name='PointsRecord_user_identity_idx'),
        ),
        migrations.RunPython(backfill_user_points_accounts, migrations.RunPython.noop),
    ]

