from datetime import datetime

import django.db.models.deletion
from django.db import migrations, models


def ensure_recommended_merchant_schema(apps, schema_editor):
    """
    兼容迁移中断导致的“表已创建但迁移未记录”场景：
    - 若执行迁移过程中数据库连接中断，可能已创建 RecommendedMerchant 表，但 django_migrations 未记录 0021；
      重新 migrate 会因 `Table 'RecommendedMerchant' already exists` 失败。

    这里按“存在则跳过，不存在则补齐”的方式保证迁移可重复执行。
    """
    RecommendedMerchant = apps.get_model('wxcloudrun', 'RecommendedMerchant')

    connection = schema_editor.connection
    existing_tables = {t.lower() for t in connection.introspection.table_names()}
    table_name = RecommendedMerchant._meta.db_table

    if table_name.lower() not in existing_tables:
        schema_editor.create_model(RecommendedMerchant)

    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, table_name)
        existing_constraint_names = {name.lower() for name in constraints.keys()}

        for index in RecommendedMerchant._meta.indexes:
            index_name = (index.name or '').lower()
            if not index_name or index_name in existing_constraint_names:
                continue
            schema_editor.add_index(RecommendedMerchant, index)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('wxcloudrun', '0020_user_feedback'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='RecommendedMerchant',
                    fields=[
                        ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('sort_order', models.PositiveIntegerField(default=1, verbose_name='排序')),
                        ('created_at', models.DateTimeField(default=datetime.now, verbose_name='创建时间')),
                        ('updated_at', models.DateTimeField(default=datetime.now, verbose_name='更新时间')),
                        ('merchant', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='recommended_entry', to='wxcloudrun.merchantprofile', verbose_name='商户')),
                    ],
                    options={
                        'db_table': 'RecommendedMerchant',
                        'verbose_name': '推荐商户',
                        'verbose_name_plural': '推荐商户',
                    },
                ),
                migrations.AddIndex(
                    model_name='recommendedmerchant',
                    index=models.Index(fields=['sort_order'], name='RecommendedMerchant_sort_order_idx'),
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(ensure_recommended_merchant_schema, migrations.RunPython.noop),
    ]

