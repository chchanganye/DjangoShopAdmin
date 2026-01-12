from datetime import datetime

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('wxcloudrun', '0023_pointsrecord_source_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='SettlementOrder',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_id', models.CharField(max_length=32, unique=True, verbose_name='订单ID')),
                ('amount', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='订单金额')),
                ('amount_int', models.IntegerField(default=0, verbose_name='结算金额(取整)')),
                ('merchant_points', models.IntegerField(default=0, verbose_name='商户积分')),
                ('owner_points', models.IntegerField(default=0, verbose_name='业主积分')),
                ('owner_rate', models.PositiveIntegerField(default=0, verbose_name='业主奖励比例(%)')),
                ('status', models.CharField(choices=[('PENDING_REVIEW', '待评价'), ('REVIEWED', '已评价')], default='PENDING_REVIEW', max_length=20, verbose_name='订单状态')),
                ('reviewed_at', models.DateTimeField(blank=True, null=True, verbose_name='评价时间')),
                ('created_at', models.DateTimeField(default=datetime.now, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(default=datetime.now, verbose_name='更新时间')),
                ('merchant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='settlement_orders', to='wxcloudrun.merchantprofile', verbose_name='商户')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='settlement_orders', to='wxcloudrun.userinfo', verbose_name='业主用户')),
            ],
            options={
                'db_table': 'SettlementOrder',
                'verbose_name': '订单结算记录',
                'verbose_name_plural': '订单结算记录',
            },
        ),
        migrations.AddIndex(
            model_name='settlementorder',
            index=models.Index(fields=['order_id'], name='SettlementOrder_order_id_idx'),
        ),
        migrations.AddIndex(
            model_name='settlementorder',
            index=models.Index(fields=['merchant'], name='SettlementOrder_merchant_idx'),
        ),
        migrations.AddIndex(
            model_name='settlementorder',
            index=models.Index(fields=['owner'], name='SettlementOrder_owner_idx'),
        ),
        migrations.AddIndex(
            model_name='settlementorder',
            index=models.Index(fields=['status'], name='SettlementOrder_status_idx'),
        ),
        migrations.AddIndex(
            model_name='settlementorder',
            index=models.Index(fields=['created_at'], name='SettlementOrder_created_at_idx'),
        ),
        migrations.CreateModel(
            name='MerchantReview',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rating', models.PositiveIntegerField(default=5, verbose_name='评分(1-5)')),
                ('content', models.CharField(blank=True, default='', max_length=500, verbose_name='评价内容')),
                ('created_at', models.DateTimeField(default=datetime.now, verbose_name='创建时间')),
                ('merchant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reviews', to='wxcloudrun.merchantprofile', verbose_name='商户')),
                ('order', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='review', to='wxcloudrun.settlementorder', verbose_name='订单')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='merchant_reviews', to='wxcloudrun.userinfo', verbose_name='业主用户')),
            ],
            options={
                'db_table': 'MerchantReview',
                'verbose_name': '商户评价',
                'verbose_name_plural': '商户评价',
            },
        ),
        migrations.AddIndex(
            model_name='merchantreview',
            index=models.Index(fields=['merchant'], name='MerchantReview_merchant_idx'),
        ),
        migrations.AddIndex(
            model_name='merchantreview',
            index=models.Index(fields=['owner'], name='MerchantReview_owner_idx'),
        ),
        migrations.AddIndex(
            model_name='merchantreview',
            index=models.Index(fields=['created_at'], name='MerchantReview_created_at_idx'),
        ),
    ]

