# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wxcloudrun', '0004_identity_application'),
    ]

    operations = [
        migrations.RenameField(
            model_name='merchantprofile',
            old_name='banner_urls',
            new_name='banner_url',
        ),
        migrations.AlterField(
            model_name='merchantprofile',
            name='banner_url',
            field=models.CharField(verbose_name='横幅展示图云文件ID', max_length=255, blank=True, default=''),
        ),
    ]

