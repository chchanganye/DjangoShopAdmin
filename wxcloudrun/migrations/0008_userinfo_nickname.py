# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wxcloudrun', '0007_add_access_log'),
    ]

    operations = [
        migrations.AddField(
            model_name='userinfo',
            name='nickname',
            field=models.CharField(verbose_name='用户昵称', max_length=100, blank=True, default=''),
        ),
    ]

