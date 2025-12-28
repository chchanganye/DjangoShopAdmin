"""小程序端联系我们相关视图"""
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import openid_required
from wxcloudrun.utils.responses import json_ok
from wxcloudrun.models import ContactSetting


@openid_required
@require_http_methods(["GET"])
def contact_info(request):
    """获取联系我们文案（可由后台随时调整）"""
    setting = ContactSetting.get_solo()
    title = (setting.title or '').strip() or '联系我们'
    content = (setting.content or '').strip()
    return json_ok({
        'title': title,
        'content': content,
        'updated_at': setting.updated_at.strftime('%Y-%m-%d %H:%M:%S') if setting.updated_at else None,
    })

