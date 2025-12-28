from django.db import migrations, models
from datetime import datetime


class Migration(migrations.Migration):

    dependencies = [
        ('wxcloudrun', '0016_merchant_location_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContactSetting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(blank=True, default='', max_length=200, verbose_name='标题')),
                ('content', models.TextField(blank=True, default='', verbose_name='文案')),
                ('created_at', models.DateTimeField(default=datetime.now, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(default=datetime.now, verbose_name='更新时间')),
            ],
            options={
                'db_table': 'ContactSetting',
                'verbose_name': '联系我们配置',
                'verbose_name_plural': '联系我们配置',
            },
        ),
    ]

