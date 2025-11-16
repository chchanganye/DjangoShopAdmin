from django.db import migrations, models
from datetime import datetime


def forwards_fill_active_identity(apps, schema_editor):
    UserInfo = apps.get_model('wxcloudrun', 'UserInfo')
    for u in UserInfo.objects.all():
        if not getattr(u, 'active_identity', None):
            u.active_identity = u.identity_type or 'OWNER'
            u.save(update_fields=['active_identity'])


class Migration(migrations.Migration):

    dependencies = [
        ('wxcloudrun', '0010_contracts_and_signatures'),
    ]

    operations = [
        migrations.AddField(
            model_name='userinfo',
            name='active_identity',
            field=models.CharField(verbose_name='活跃身份', max_length=20, choices=(('OWNER','业主'),('PROPERTY','物业'),('MERCHANT','商户'),('ADMIN','管理员')), default='OWNER'),
        ),
        migrations.CreateModel(
            name='UserAssignedIdentity',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('identity_type', models.CharField(verbose_name='身份类型', max_length=20, choices=(('OWNER','业主'),('PROPERTY','物业'),('MERCHANT','商户'),('ADMIN','管理员')))),
                ('created_at', models.DateTimeField(verbose_name='创建时间', default=datetime.now)),
                ('user', models.ForeignKey(on_delete=models.CASCADE, related_name='assigned_identities', to='wxcloudrun.userinfo', verbose_name='用户')),
            ],
            options={
                'db_table': 'UserAssignedIdentity',
                'verbose_name': '用户赋予身份',
                'verbose_name_plural': '用户赋予身份',
            },
        ),
        migrations.AddIndex(
            model_name='userassignedidentity',
            index=models.Index(fields=['user', 'identity_type'], name='UserAssign_user_ident_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='userassignedidentity',
            unique_together={('user', 'identity_type')},
        ),
        migrations.RunPython(forwards_fill_active_identity, migrations.RunPython.noop),
    ]