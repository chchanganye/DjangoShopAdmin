"""视图装饰器"""
import logging
from wxcloudrun.utils.auth import get_openid, ensure_userinfo_exists, get_admin_from_token
from wxcloudrun.utils.responses import json_err


logger = logging.getLogger('log')


def openid_required(view_func):
    """仅校验 OpenID 是否存在，存在则放行。不做身份或权限校验。
    适用于小程序通过 wx.cloud.callContainer 自动注入请求头的场景。
    """
    def _wrapped(request, *args, **kwargs):
        # 管理员Token优先直通
        admin = get_admin_from_token(request)
        if admin:
            return view_func(request, *args, **kwargs)

        openid = get_openid(request)
        if not openid:
            return json_err('缺少openid', status=401)
        try:
            ensure_userinfo_exists(openid)
        except Exception as exc:
            logger.error(f'自动创建用户失败: openid={openid}, error={exc}', exc_info=True)
            return json_err('初始化用户失败', status=500)
        return view_func(request, *args, **kwargs)
    return _wrapped


def admin_token_required(view_func):
    """仅允许持有有效管理员 Token 的请求通过。"""
    def _wrapped(request, *args, **kwargs):
        admin = get_admin_from_token(request)
        if not admin:
            return json_err('未认证或无权限', status=401)
        return view_func(request, admin=admin, *args, **kwargs)
    return _wrapped

