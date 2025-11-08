"""管理员认证视图"""
import json
import logging
from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate
from rest_framework.authtoken.models import Token

from wxcloudrun.utils.responses import json_ok, json_err


logger = logging.getLogger('log')


@require_http_methods(["POST"])
def admin_login(request):
    """管理员登录，返回Token。
    请求体示例：{"username":"admin","password":"123456"}
    """
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    username = body.get('username')
    password = body.get('password')
    if not username or not password:
        return json_err('缺少参数 username 或 password', status=400)
    user = authenticate(username=username, password=password)
    if not user:
        return json_err('用户名或密码错误', status=401)
    # 仅允许超级用户获取管理员Token
    if not user.is_superuser:
        return json_err('仅允许超级用户登录', status=403)
    token, _ = Token.objects.get_or_create(user=user)
    return json_ok({'token': token.key, 'username': username})

