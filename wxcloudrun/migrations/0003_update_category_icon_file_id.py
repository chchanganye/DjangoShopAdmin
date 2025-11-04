from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wxcloudrun', '0002_drop_counters'),
    ]

    operations = [
        migrations.RenameField(
            model_name='category',
            old_name='icon_name',
            new_name='icon_file_id',
        ),
        migrations.AlterField(
            model_name='category',
            name='icon_file_id',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='图标文件ID'),
        ),
    ]

