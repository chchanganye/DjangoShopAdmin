from datetime import datetime

import django.db.models.deletion
from django.db import migrations, models


def seed_communities_from_properties(apps, schema_editor):
    """
    将历史 PropertyProfile.community_name 迁移为 Community 记录，便于旧数据平滑过渡：
    - 对每个存在 community_name 的物业档案创建一条小区记录
    - 对已绑定该物业的业主用户，自动补齐 owner_community
    """
    PropertyProfile = apps.get_model('wxcloudrun', 'PropertyProfile')
    Community = apps.get_model('wxcloudrun', 'Community')
    UserInfo = apps.get_model('wxcloudrun', 'UserInfo')

    now = datetime.now()
    counter = 1
    existing_ids = set(Community.objects.values_list('community_id', flat=True))

    def next_community_id() -> str:
        nonlocal counter
        while True:
            cid = f"COMMUNITY_{str(counter).zfill(3)}"
            counter += 1
            if cid not in existing_ids:
                existing_ids.add(cid)
                return cid

    properties = PropertyProfile.objects.all().order_by('id')
    for prop in properties:
        community_name = (getattr(prop, 'community_name', '') or '').strip()
        if not community_name:
            continue

        record = Community.objects.filter(property=prop, community_name=community_name).first()
        if not record:
            record = Community.objects.create(
                property=prop,
                community_id=next_community_id(),
                community_name=community_name,
                created_at=now,
                updated_at=now,
            )

        UserInfo.objects.filter(owner_property=prop, owner_community__isnull=True).update(owner_community=record)


class Migration(migrations.Migration):
    dependencies = [
        ('wxcloudrun', '0018_points_share_setting_owner_reward_rate'),
    ]

    operations = [
        migrations.CreateModel(
            name='Community',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('community_id', models.CharField(max_length=32, unique=True, verbose_name='小区ID')),
                ('community_name', models.CharField(max_length=200, verbose_name='小区名称')),
                ('created_at', models.DateTimeField(default=datetime.now, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(default=datetime.now, verbose_name='更新时间')),
                ('property', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='communities', to='wxcloudrun.propertyprofile', verbose_name='所属物业')),
            ],
            options={
                'db_table': 'Community',
                'verbose_name': '小区信息',
                'verbose_name_plural': '小区信息',
            },
        ),
        migrations.AddIndex(
            model_name='community',
            index=models.Index(fields=['community_id'], name='Community_community_id_idx'),
        ),
        migrations.AddIndex(
            model_name='community',
            index=models.Index(fields=['property'], name='Community_property_idx'),
        ),
        migrations.AddIndex(
            model_name='community',
            index=models.Index(fields=['community_name'], name='Community_community_name_idx'),
        ),
        migrations.AddField(
            model_name='userinfo',
            name='owner_community',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='community_owners', to='wxcloudrun.community', verbose_name='所属小区'),
        ),
        migrations.RunPython(seed_communities_from_properties, migrations.RunPython.noop),
    ]

