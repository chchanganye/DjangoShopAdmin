from datetime import datetime

import django.db.models.deletion
from django.db import migrations, models


def ensure_community_schema(apps, schema_editor):
    """
    兼容迁移中断导致的“表已创建但迁移未记录”场景：
    - 若执行迁移过程中数据库连接中断，可能已创建 Community 表，但 django_migrations 中未记录 0019；
      重新 migrate 会因 `Table 'Community' already exists` 失败。
    - 同时可能缺失 UserInfo.owner_community_id 字段，导致线上查询报错。

    这里按“存在则跳过，不存在则补齐”的方式，把表 / 字段 / 索引补齐，保证迁移可重复执行。
    """
    Community = apps.get_model('wxcloudrun', 'Community')
    UserInfo = apps.get_model('wxcloudrun', 'UserInfo')

    connection = schema_editor.connection
    existing_tables = {t.lower() for t in connection.introspection.table_names()}

    community_table = Community._meta.db_table
    userinfo_table = UserInfo._meta.db_table

    if community_table.lower() not in existing_tables:
        schema_editor.create_model(Community)

    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, community_table)
        existing_constraint_names = {name.lower() for name in constraints.keys()}

        for index in Community._meta.indexes:
            index_name = (index.name or '').lower()
            if not index_name or index_name in existing_constraint_names:
                continue
            schema_editor.add_index(Community, index)

        columns = {
            c.name
            for c in connection.introspection.get_table_description(cursor, userinfo_table)
        }
        if 'owner_community_id' not in columns:
            field = UserInfo._meta.get_field('owner_community')
            schema_editor.add_field(UserInfo, field)


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
    atomic = False

    dependencies = [
        ('wxcloudrun', '0018_points_share_setting_owner_reward_rate'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
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
            ],
            database_operations=[],
        ),
        migrations.RunPython(ensure_community_schema, migrations.RunPython.noop),
        migrations.RunPython(seed_communities_from_properties, migrations.RunPython.noop),
    ]
