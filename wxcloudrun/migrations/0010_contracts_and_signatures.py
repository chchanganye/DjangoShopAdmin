from django.db import migrations, models
import django.db.models.deletion
from datetime import datetime


class Migration(migrations.Migration):

    dependencies = [
        ('wxcloudrun', '0009_merchant_extra_fields'),
    ]

    database_operations = [
        # 实际数据库变更：创建 ContractSetting 与 UserContractSignature
        migrations.CreateModel(
            name='ContractSetting',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('contract_file_id', models.CharField(verbose_name='协议合同云文件ID', max_length=255, blank=True, default='')),
                ('created_at', models.DateTimeField(verbose_name='创建时间', default=datetime.now)),
                ('updated_at', models.DateTimeField(verbose_name='更新时间', default=datetime.now)),
            ],
            options={
                'db_table': 'ContractSetting',
                'verbose_name': '协议合同配置',
                'verbose_name_plural': '协议合同配置',
            },
        ),
        migrations.CreateModel(
            name='UserContractSignature',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('contract_file_id', models.CharField(verbose_name='签署时的合同云文件ID', max_length=255)),
                ('signature_file_id', models.CharField(verbose_name='签名云文件ID', max_length=255, blank=True, default='')),
                ('signed_at', models.DateTimeField(verbose_name='签署时间', default=datetime.now)),
                ('updated_at', models.DateTimeField(verbose_name='更新时间', default=datetime.now)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contract_signatures', to='wxcloudrun.userinfo', verbose_name='用户')),
            ],
            options={
                'db_table': 'UserContractSignature',
                'verbose_name': '用户合同签名',
                'verbose_name_plural': '用户合同签名',
            },
        ),
        migrations.AddIndex(
            model_name='usercontractsignature',
            index=models.Index(fields=['user', 'contract_file_id'], name='UserContrac_user_contract_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='usercontractsignature',
            unique_together={('user', 'contract_file_id')},
        ),
    ]

    state_operations = [
        # 仅迁移状态：标记 PointsShareSetting 已存在，避免重复创建表
        migrations.CreateModel(
            name='PointsShareSetting',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('merchant_rate', models.PositiveIntegerField(verbose_name='商户积分比例(%)', default=90)),
                ('created_at', models.DateTimeField(verbose_name='创建时间', default=datetime.now)),
                ('updated_at', models.DateTimeField(verbose_name='更新时间', default=datetime.now)),
            ],
            options={
                'db_table': 'PointsShareSetting',
                'verbose_name': '积分分成配置',
                'verbose_name_plural': '积分分成配置',
            },
        ),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=database_operations,
            state_operations=state_operations,
        )
    ]