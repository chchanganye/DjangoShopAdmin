"""管理员联系我们文案管理视图"""
import json

from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import admin_token_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.models import ContactSetting


@admin_token_required
@require_http_methods(["GET", "PUT"])
def admin_contact_info(request, admin):
    """联系我们文案 - GET查询 / PUT更新"""
    setting = ContactSetting.get_solo()

    if request.method == "GET":
        return json_ok({
            'title': setting.title or '',
            'content': setting.content or '',
            'updated_at': setting.updated_at.strftime('%Y-%m-%d %H:%M:%S') if setting.updated_at else None,
        })

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)

    if 'title' in body:
        setting.title = (body.get('title') or '').strip()
    if 'content' in body:
        setting.content = body.get('content') or ''

    setting.save()
    return json_ok({
        'title': setting.title or '',
        'content': setting.content or '',
        'updated_at': setting.updated_at.strftime('%Y-%m-%d %H:%M:%S') if setting.updated_at else None,
    })

