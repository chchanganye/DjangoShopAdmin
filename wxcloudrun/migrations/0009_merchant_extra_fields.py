from django.db import migrations, models


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
    ]
