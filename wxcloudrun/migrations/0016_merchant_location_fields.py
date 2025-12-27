from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wxcloudrun', '0015_merchant_business_license_file_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchantprofile',
            name='latitude',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=10, null=True, verbose_name='纬度'),
        ),
        migrations.AddField(
            model_name='merchantprofile',
            name='longitude',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=10, null=True, verbose_name='经度'),
        ),
    ]

