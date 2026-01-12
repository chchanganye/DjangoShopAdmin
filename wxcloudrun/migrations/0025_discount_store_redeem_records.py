from datetime import datetime

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('wxcloudrun', '0024_orders_and_reviews'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchantprofile',
            name='merchant_type',
            field=models.CharField(choices=[('NORMAL', '普通商户'), ('DISCOUNT_STORE', '折扣店')], default='NORMAL', max_length=20, verbose_name='商户类型'),
        ),
        migrations.AddField(
            model_name='identityapplication',
            name='merchant_type',
            field=models.CharField(blank=True, choices=[('NORMAL', '普通商户'), ('DISCOUNT_STORE', '折扣店')], default='NORMAL', max_length=20, verbose_name='商户类型'),
        ),
        migrations.CreateModel(
            name='DiscountRedeemRecord',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('redeem_id', models.CharField(max_length=32, unique=True, verbose_name='兑换ID')),
                ('owner_phone_number', models.CharField(blank=True, default='', max_length=32, verbose_name='业主手机号')),
                ('points', models.PositiveIntegerField(default=0, verbose_name='兑换积分')),
                ('created_at', models.DateTimeField(default=datetime.now, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(default=datetime.now, verbose_name='更新时间')),
                ('merchant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='discount_redeem_records', to='wxcloudrun.merchantprofile', verbose_name='折扣店商户')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='discount_redeem_records', to='wxcloudrun.userinfo', verbose_name='业主用户')),
            ],
            options={
                'db_table': 'DiscountRedeemRecord',
                'verbose_name': '折扣店兑换记录',
                'verbose_name_plural': '折扣店兑换记录',
            },
        ),
        migrations.AddIndex(
            model_name='discountredeemrecord',
            index=models.Index(fields=['redeem_id'], name='DRR_redeem_id_idx'),
        ),
        migrations.AddIndex(
            model_name='discountredeemrecord',
            index=models.Index(fields=['merchant'], name='DRR_merchant_idx'),
        ),
        migrations.AddIndex(
            model_name='discountredeemrecord',
            index=models.Index(fields=['owner'], name='DRR_owner_idx'),
        ),
        migrations.AddIndex(
            model_name='discountredeemrecord',
            index=models.Index(fields=['created_at'], name='DRR_created_at_idx'),
        ),
    ]
