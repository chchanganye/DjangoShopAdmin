"""对象存储服务"""
import os
import logging
import requests
from wxcloudrun.exceptions import WxOpenApiError


logger = logging.getLogger('log')

WX_OPENAPI_BASE = os.environ.get('WX_OPENAPI_BASE', 'http://api.weixin.qq.com')
WX_ENV_ID = os.environ.get('CLOUD_ID')


def wx_openapi_post(path: str, payload: dict):
    """调用微信开放接口"""
    if not WX_ENV_ID:
        raise WxOpenApiError('未配置 CLOUD_ID 环境变量')

    url = f"{WX_OPENAPI_BASE.rstrip('/')}/{path.lstrip('/')}"
    headers = {'Content-Type': 'application/json'}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        logger.error(f'请求微信开放接口失败: {path}, error={exc}')
        raise WxOpenApiError('调用微信开放接口失败') from exc

    try:
        data = resp.json()
    except ValueError as exc:
        logger.error(f'解析微信开放接口响应失败: {path}, resp={resp.text}')
        raise WxOpenApiError('微信开放接口返回格式错误') from exc

    if data.get('errcode') != 0:
        logger.error(f'微信开放接口返回错误: {path}, payload={payload}, resp={data}')
        raise WxOpenApiError(data.get('errmsg') or '微信开放接口返回错误')
    return data


def get_temp_file_urls(file_ids):
    """批量获取临时下载URL"""
    if not file_ids:
        return {}
    try:
        data = wx_openapi_post('tcb/batchdownloadfile', {
            'env': WX_ENV_ID,
            'file_list': [{'fileid': fid, 'max_age': 7200} for fid in file_ids],
        })
    except WxOpenApiError:
        return {}

    url_map = {}
    for item in data.get('file_list', []):
        if item.get('status') == 0:
            url_map[item['fileid']] = item.get('download_url')
    return url_map


def resolve_icon_url(icon_value, temp_map=None):
    """解析图标URL"""
    if not icon_value:
        return ''
    if icon_value.startswith('cloud://'):
        return (temp_map or {}).get(icon_value, '')
    if icon_value.startswith('http://') or icon_value.startswith('https://'):
        return icon_value
    return ''


def delete_cloud_files(file_ids):
    """批量删除云存储文件"""
    if not file_ids:
        return
    wx_openapi_post('tcb/batchdeletefile', {
        'env': WX_ENV_ID,
        'fileid_list': file_ids,
    })


def generate_storage_path(filename: str, directory: str = 'category-icons') -> str:
    """生成存储路径"""
    import uuid
    ext = filename.rsplit('.', 1)[-1] if '.' in filename else 'png'
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    return f"{directory}/{unique_name}"

