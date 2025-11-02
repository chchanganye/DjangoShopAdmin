from django.apps import AppConfig


class AppNameConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'wxcloudrun'
    # 在 Django Admin 中显示为中文分组名称
    verbose_name = 'wxcloudrun 业务模型'
