import datetime
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('wxcloudrun', '0008_userinfo_nickname'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchantprofile',
            name='avg_score',
            field=models.DecimalField(decimal_places=1, default=0, max_digits=3, verbose_name='平均评分'),
        ),
        migrations.AddField(
            model_name='merchantprofile',
            name='gallery',
            field=models.JSONField(blank=True, default=list, verbose_name='图集'),
        ),
        migrations.AddField(
            model_name='merchantprofile',
            name='open_hours',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='营业时间'),
        ),
        migrations.AddField(
            model_name='merchantprofile',
            name='rating_count',
            field=models.PositiveIntegerField(default=0, verbose_name='评分次数'),
        ),
        migrations.CreateModel(
            name='MerchantFavorite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(default=datetime.datetime.now, verbose_name='创建时间')),
                ('merchant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='favorites', to='wxcloudrun.merchantprofile', verbose_name='商户')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='merchant_favorites', to='wxcloudrun.userinfo', verbose_name='用户')),
            ],
            options={
                'verbose_name': '商户收藏',
                'verbose_name_plural': '商户收藏',
                'db_table': 'MerchantFavorite',
                'unique_together': {('merchant', 'user')},
            },
        ),
        migrations.CreateModel(
            name='MerchantBooking',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('service_id', models.CharField(max_length=64, verbose_name='服务ID')),
                ('appointment_time', models.DateTimeField(verbose_name='预约时间')),
                ('remark', models.CharField(blank=True, default='', max_length=500, verbose_name='备注')),
                ('status', models.CharField(choices=[('PENDING', '待处理'), ('CONFIRMED', '已确认'), ('CANCELLED', '已取消'), ('COMPLETED', '已完成')], default='PENDING', max_length=20, verbose_name='状态')),
                ('created_at', models.DateTimeField(default=datetime.datetime.now, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(default=datetime.datetime.now, verbose_name='更新时间')),
                ('merchant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bookings', to='wxcloudrun.merchantprofile', verbose_name='商户')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='merchant_bookings', to='wxcloudrun.userinfo', verbose_name='用户')),
            ],
            options={
                'verbose_name': '商户预约',
                'verbose_name_plural': '商户预约',
                'db_table': 'MerchantBooking',
            },
        ),
        migrations.AddIndex(
            model_name='merchantfavorite',
            index=models.Index(fields=['merchant', 'user'], name='MerchantFav_merchant_713c1d_idx'),
        ),
        migrations.AddIndex(
            model_name='merchantfavorite',
            index=models.Index(fields=['user'], name='MerchantFav_user_id_idx'),
        ),
        migrations.AddIndex(
            model_name='merchantbooking',
            index=models.Index(fields=['merchant', 'appointment_time'], name='MerchantBoo_merchant_99bb73_idx'),
        ),
        migrations.AddIndex(
            model_name='merchantbooking',
            index=models.Index(fields=['user'], name='MerchantBoo_user_id_idx'),
        ),
    ]
