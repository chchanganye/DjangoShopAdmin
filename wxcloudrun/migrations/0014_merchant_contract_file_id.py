from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wxcloudrun', '0013_backfill_assigned_identities'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchantprofile',
            name='contract_file_id',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='商户合同云文件ID'),
        ),
    ]

