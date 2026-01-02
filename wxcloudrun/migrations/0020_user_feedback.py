from datetime import datetime

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('wxcloudrun', '0019_community_and_owner_community'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserFeedback',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content', models.TextField(default='', verbose_name='反馈内容')),
                ('images', models.JSONField(blank=True, default=list, verbose_name='图片')),
                ('created_at', models.DateTimeField(default=datetime.now, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(default=datetime.now, verbose_name='更新时间')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='feedbacks', to='wxcloudrun.userinfo', verbose_name='用户')),
            ],
            options={
                'db_table': 'UserFeedback',
                'verbose_name': '意见反馈',
                'verbose_name_plural': '意见反馈',
            },
        ),
        migrations.AddIndex(
            model_name='userfeedback',
            index=models.Index(fields=['user'], name='UserFeedback_user_idx'),
        ),
        migrations.AddIndex(
            model_name='userfeedback',
            index=models.Index(fields=['created_at'], name='UserFeedback_created_at_idx'),
        ),
    ]

