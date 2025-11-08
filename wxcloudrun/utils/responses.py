"""统一响应工具"""
from django.http import JsonResponse


def json_ok(data=None, status=200, message='success'):
    """统一成功响应结构
    - code: 业务状态码，默认等于 HTTP 状态码（200/201/204等）
    - msg: 人类可读提示，默认 'success'
    - data: 成功时返回的数据；若传入 None，返回空对象 {}
    """
    payload = {
        'code': status,
        'msg': message,
        'data': {} if data is None else data,
    }
    return JsonResponse(payload, status=status, json_dumps_params={'ensure_ascii': False})


def json_err(message='错误', code=None, status=400):
    """统一错误响应结构
    - code: 业务状态码，默认等于 HTTP 状态码（400/401/403/404/500等）
    - msg: 错误信息
    - data: 错误时固定为 None
    """
    payload = {
        'code': code or status,
        'msg': message,
        'data': None,
    }
    return JsonResponse(payload, status=status, json_dumps_params={'ensure_ascii': False})

