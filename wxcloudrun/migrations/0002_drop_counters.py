from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('wxcloudrun', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS `Counters`;",
            reverse_sql=migrations.RunSQL.noop
        ),
    ]