# Generated manually

from django.db import migrations, models
import datetime


class Migration(migrations.Migration):

    dependencies = [
        ('wxcloudrun', '0006_change_banner_to_single'),
    ]

    operations = [
        migrations.CreateModel(
            name='AccessLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('openid', models.CharField(db_index=True, max_length=128, verbose_name='用户OpenID')),
                ('access_date', models.DateField(db_index=True, default=datetime.date.today, verbose_name='访问日期')),
                ('access_count', models.IntegerField(default=1, verbose_name='当日访问次数')),
                ('first_access_at', models.DateTimeField(default=datetime.datetime.now, verbose_name='首次访问时间')),
                ('last_access_at', models.DateTimeField(default=datetime.datetime.now, verbose_name='最后访问时间')),
            ],
            options={
                'verbose_name': '访问日志',
                'verbose_name_plural': '访问日志',
                'db_table': 'AccessLog',
                'indexes': [
                    models.Index(fields=['access_date'], name='AccessLog_access_d_idx'),
                    models.Index(fields=['openid', 'access_date'], name='AccessLog_openid_access_idx'),
                ],
                'unique_together': {('openid', 'access_date')},
            },
        ),
    ]

