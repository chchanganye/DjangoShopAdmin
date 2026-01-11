from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wxcloudrun', '0022_user_points_accounts'),
    ]

    operations = [
        migrations.AddField(
            model_name='pointsrecord',
            name='source_type',
            field=models.CharField(blank=True, default='', max_length=50, verbose_name='积分来源'),
        ),
        migrations.AddField(
            model_name='pointsrecord',
            name='source_meta',
            field=models.JSONField(blank=True, default=dict, verbose_name='来源详情'),
        ),
        migrations.AddIndex(
            model_name='pointsrecord',
            index=models.Index(fields=['created_at'], name='PointsRecord_created_at_idx'),
        ),
    ]

