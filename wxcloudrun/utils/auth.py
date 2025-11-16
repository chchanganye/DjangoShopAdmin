"""认证工具函数"""
import logging
from rest_framework.authtoken.models import Token
from wxcloudrun.models import UserInfo, UserAssignedIdentity


logger = logging.getLogger('log')


def get_openid(request):
    """仅从 request.headers 读取微信云托管注入的 OpenID，不做任何回退或兼容逻辑。"""
    return request.headers.get('X-WX-OPENID')


def ensure_userinfo_exists(openid: str) -> UserInfo:
    user, created = UserInfo.objects.get_or_create(
        openid=openid,
        defaults={'identity_type': 'OWNER', 'active_identity': 'OWNER'},
    )
    try:
        UserAssignedIdentity.objects.get_or_create(user=user, identity_type='OWNER')
    except Exception:
        pass
    if created:
        logger.info(f'自动创建小程序用户: openid={openid}')
    return user


def parse_auth_header(request):
    """从 Authorization 头中解析出可能的 Token 值。
    支持格式：
      - Authorization: Token <key>
      - Authorization: Bearer <key>
      - Authorization: token <key>
    返回 token_key 或 None。
    """
    auth = request.headers.get('Authorization') or request.META.get('HTTP_AUTHORIZATION')
    if not auth:
        return None
    parts = auth.strip().split()
    if len(parts) == 2 and parts[0].lower() in ('token', 'bearer'):
        return parts[1]
    # 仅有纯token的情况
    if len(parts) == 1:
        return parts[0]
    return None


def get_admin_from_token(request):
    """校验 Authorization Token 并返回 Django 用户（仅限管理员）。
    仅当 user.is_superuser 为真时视为管理员。验证失败返回 None。
    """
    token_key = parse_auth_header(request)
    if not token_key:
        return None
    try:
        token = Token.objects.select_related('user').get(key=token_key)
        user = token.user
        if user and user.is_superuser:
            return user
        return None
    except Token.DoesNotExist:
        return None

