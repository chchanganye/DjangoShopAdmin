from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from datetime import datetime


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('wxcloudrun', '0003_update_category_icon_file_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='IdentityApplication',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('requested_identity', models.CharField(choices=[('OWNER', '业主'), ('PROPERTY', '物业'), ('MERCHANT', '商户'), ('ADMIN', '管理员')], max_length=20, verbose_name='申请身份')),
                ('status', models.CharField(choices=[('PENDING', '待审核'), ('APPROVED', '已批准'), ('REJECTED', '已拒绝')], default='PENDING', max_length=20, verbose_name='审核状态')),
                ('owner_property_id', models.CharField(blank=True, default='', max_length=32, verbose_name='申请的物业ID')),
                ('merchant_name', models.CharField(blank=True, default='', max_length=200, verbose_name='商户名称')),
                ('merchant_description', models.TextField(blank=True, default='', verbose_name='商户简介')),
                ('merchant_address', models.CharField(blank=True, default='', max_length=300, verbose_name='商户地址')),
                ('merchant_phone', models.CharField(blank=True, default='', max_length=32, verbose_name='商户联系电话')),
                ('property_name', models.CharField(blank=True, default='', max_length=200, verbose_name='物业名称')),
                ('property_community', models.CharField(blank=True, default='', max_length=200, verbose_name='社区名称')),
                ('reviewed_at', models.DateTimeField(blank=True, null=True, verbose_name='审核时间')),
                ('reject_reason', models.TextField(blank=True, default='', verbose_name='拒绝原因')),
                ('created_at', models.DateTimeField(default=datetime.now, verbose_name='申请时间')),
                ('updated_at', models.DateTimeField(default=datetime.now, verbose_name='更新时间')),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviewed_applications', to=settings.AUTH_USER_MODEL, verbose_name='审核人')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='identity_applications', to='wxcloudrun.userinfo', verbose_name='申请用户')),
            ],
            options={
                'verbose_name': '身份申请',
                'verbose_name_plural': '身份申请',
                'db_table': 'IdentityApplication',
            },
        ),
        migrations.AddIndex(
            model_name='identityapplication',
            index=models.Index(fields=['user', 'status'], name='IdentityApp_user_id_33dd26_idx'),
        ),
        migrations.AddIndex(
            model_name='identityapplication',
            index=models.Index(fields=['status', 'created_at'], name='IdentityApp_status_9c7b53_idx'),
        ),
    ]

