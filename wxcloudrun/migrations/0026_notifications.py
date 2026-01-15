from datetime import datetime

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('wxcloudrun', '0025_discount_store_redeem_records'),
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200, verbose_name='通知标题')),
                ('content', models.TextField(default='', verbose_name='通知内容')),
                ('created_at', models.DateTimeField(default=datetime.now, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(default=datetime.now, verbose_name='更新时间')),
            ],
            options={
                'db_table': 'Notification',
                'verbose_name': '通知',
                'verbose_name_plural': '通知',
            },
        ),
        migrations.CreateModel(
            name='NotificationRead',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('read_at', models.DateTimeField(default=datetime.now, verbose_name='阅读时间')),
                ('notification', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reads', to='wxcloudrun.notification', verbose_name='通知')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notification_reads', to='wxcloudrun.userinfo', verbose_name='用户')),
            ],
            options={
                'db_table': 'NotificationRead',
                'verbose_name': '通知阅读记录',
                'verbose_name_plural': '通知阅读记录',
                'unique_together': {('notification', 'user')},
            },
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['created_at'], name='Notification_created_at_idx'),
        ),
        migrations.AddIndex(
            model_name='notificationread',
            index=models.Index(fields=['user'], name='NotificationRead_user_idx'),
        ),
        migrations.AddIndex(
            model_name='notificationread',
            index=models.Index(fields=['notification'], name='NotificationRead_notice_idx'),
        ),
        migrations.AddIndex(
            model_name='notificationread',
            index=models.Index(fields=['read_at'], name='NotificationRead_read_at_idx'),
        ),
    ]
