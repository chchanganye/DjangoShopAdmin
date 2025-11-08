"""管理员存储管理视图"""
import json
import logging
import os
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import admin_token_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.exceptions import WxOpenApiError
from wxcloudrun.services.storage_service import wx_openapi_post, generate_storage_path


logger = logging.getLogger('log')

WX_ENV_ID = os.environ.get('CLOUD_ID')


@admin_token_required
@require_http_methods(["POST"])
def admin_storage_upload_credential(request, admin):
    """获取对象存储上传凭证"""
    if not WX_ENV_ID:
        return json_err('未配置存储环境变量 CLOUD_ID', status=500)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)

    filename = body.get('filename', '') or ''
    directory = body.get('directory', 'category-icons')
    custom_path = body.get('path')

    if custom_path:
        storage_path = custom_path.lstrip('/')
    else:
        storage_path = generate_storage_path(filename, directory)

    try:
        data = wx_openapi_post('tcb/uploadfile', {
            'env': WX_ENV_ID,
            'path': storage_path,
        })
    except WxOpenApiError as exc:
        return json_err(str(exc) or '获取上传凭证失败', status=500)

    return json_ok({
        'file_id': data.get('file_id'),
        'upload_url': data.get('url'),
        'authorization': data.get('authorization'),
        'token': data.get('token'),
        'cos_file_id': data.get('cos_file_id'),
        'path': storage_path,
        'expires_in': data.get('expired_time'),
    })


@admin_token_required
@require_http_methods(["POST"])
def admin_storage_delete_files(request, admin):
    """批量删除对象存储文件"""
    if not WX_ENV_ID:
        return json_err('未配置存储环境变量 CLOUD_ID', status=500)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)

    file_ids = body.get('file_ids')
    if not file_ids or not isinstance(file_ids, list):
        return json_err('缺少参数 file_ids', status=400)

    try:
        data = wx_openapi_post('tcb/batchdeletefile', {
            'env': WX_ENV_ID,
            'fileid_list': file_ids,
        })
    except WxOpenApiError as exc:
        return json_err(str(exc) or '删除文件失败', status=500)

    return json_ok({
        'deleted': file_ids,
        'result': data.get('delete_list', []),
    })

