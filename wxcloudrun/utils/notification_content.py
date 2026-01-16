"""Notification content helpers for image handling."""
from __future__ import annotations

import re
from typing import Iterable


IMG_TAG_RE = re.compile(r'<img\b[^>]*>', re.IGNORECASE)
SRC_RE = re.compile(r'\bsrc=["\']([^"\']+)["\']', re.IGNORECASE)
DATA_FILE_RE = re.compile(r'\bdata-file-id=["\']([^"\']+)["\']', re.IGNORECASE)
DATA_FILE_SHORT_RE = re.compile(r'\bdata-fileid=["\']([^"\']+)["\']', re.IGNORECASE)
ALT_RE = re.compile(r'\balt=["\']([^"\']*)["\']', re.IGNORECASE)


def _get_attr(match_re: re.Pattern, tag: str) -> str:
    match = match_re.search(tag)
    return match.group(1) if match else ''


def _ensure_attr(tag: str, attr: str, value: str) -> str:
    pattern = re.compile(rf'\b{re.escape(attr)}=["\']([^"\']+)["\']', re.IGNORECASE)
    if pattern.search(tag):
        return pattern.sub(f'{attr}="{value}"', tag, count=1)
    if tag.endswith('/>'):
        return tag[:-2] + f' {attr}="{value}" />'
    return tag[:-1] + f' {attr}="{value}">'


def _ensure_src(tag: str, value: str) -> str:
    if SRC_RE.search(tag):
        return SRC_RE.sub(f'src="{value}"', tag, count=1)
    return _ensure_attr(tag, 'src', value)


def _pick_file_id(tag: str) -> str:
    data_file_id = _get_attr(DATA_FILE_RE, tag)
    if data_file_id and data_file_id.startswith('cloud://'):
        return data_file_id
    data_file_id = _get_attr(DATA_FILE_SHORT_RE, tag)
    if data_file_id and data_file_id.startswith('cloud://'):
        return data_file_id
    alt = _get_attr(ALT_RE, tag)
    if alt and alt.startswith('cloud://'):
        return alt
    src = _get_attr(SRC_RE, tag)
    if src and src.startswith('cloud://'):
        return src
    return ''


def extract_image_file_ids(content: str) -> list[str]:
    """Collect cloud file ids from <img> tags."""
    file_ids: list[str] = []
    for tag in IMG_TAG_RE.findall(content or ''):
        file_id = _pick_file_id(tag)
        if file_id:
            file_ids.append(file_id)
    return file_ids


def normalize_content(content: str) -> str:
    """Replace image src with cloud file id when data-file-id is present."""
    def _replace(match: re.Match) -> str:
        tag = match.group(0)
        file_id = _pick_file_id(tag)
        if not file_id:
            return tag
        tag = _ensure_attr(tag, 'data-file-id', file_id)
        tag = _ensure_attr(tag, 'data-fileid', file_id)
        tag = _ensure_attr(tag, 'alt', file_id)
        return _ensure_src(tag, file_id)

    return IMG_TAG_RE.sub(_replace, content or '')


def render_content(content: str, url_map: dict[str, str]) -> str:
    """Replace image src with temp url and keep data-file-id."""
    def _replace(match: re.Match) -> str:
        tag = match.group(0)
        file_id = _pick_file_id(tag)
        if not file_id:
            return tag
        temp_url = url_map.get(file_id)
        if not temp_url:
            return tag
        tag = _ensure_attr(tag, 'data-file-id', file_id)
        tag = _ensure_attr(tag, 'data-fileid', file_id)
        tag = _ensure_attr(tag, 'alt', file_id)
        return _ensure_src(tag, temp_url)

    return IMG_TAG_RE.sub(_replace, content or '')


def dedupe_file_ids(file_ids: Iterable[str]) -> list[str]:
    seen = set()
    result = []
    for fid in file_ids:
        if fid in seen:
            continue
        seen.add(fid)
        result.append(fid)
    return result
