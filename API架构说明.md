# 微信小程序后台管理系统 - API 架构说明

## 📐 系统架构

```
┌──────────────────────────────────────────┐
│  微信小程序前端                           │
│  - 通过 wx.cloud.callContainer 调用      │
│  - 自动注入 X-WX-OPENID 头               │
└──────────────┬───────────────────────────┘
               │
               ↓
┌──────────────────────────────────────────┐
│  Vue 管理后台                             │
│  - Token 认证                             │
│  - Authorization: Token xxx               │
└──────────────┬───────────────────────────┘
               │
               ↓
┌──────────────────────────────────────────┐
│  Django Backend API                       │
│  ├─ openid_required (小程序)              │
│  │  └─ 验证 X-WX-OPENID                   │
│  └─ admin_token_required (管理员)         │
│     └─ 验证 Token + is_superuser          │
└──────────────────────────────────────────┘
```

## 🔐 认证方式

### 1. 小程序 OpenID 认证（`openid_required`）

**适用场景**：微信小程序通过云托管调用

**验证方式**：
- 读取请求头 `X-WX-OPENID`（由微信云托管自动注入）
- 不需要额外的 token 或密码

**装饰器示例**：
```python
@openid_required
@require_http_methods(["GET"])
def categories_list(request):
    # request 会自动通过 OpenID 验证
    pass
```

### 2. 管理员 Token 认证（`admin_token_required`）

**适用场景**：Vue 管理后台调用

**验证方式**：
- 读取请求头 `Authorization: Token <key>` 或 `Authorization: Bearer <key>`
- 验证 Token 是否有效
- 验证用户是否为超级管理员（`is_superuser=True`）

**装饰器示例**：
```python
@admin_token_required
@require_http_methods(["GET"])
def users_list(request, admin):
    # admin 参数为验证通过的 Django User 对象
    pass
```

## 📋 统一响应格式

### 成功响应

```json
{
  "code": 200,
  "msg": "success",
  "data": { ... }
}
```

### 错误响应

```json
{
  "code": 400,
  "msg": "错误信息",
  "data": null
}
```

## 🛣️ API 路由分类

### 小程序公开接口（OpenID 认证）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/categories` | 获取商品分类列表 |
| GET | `/api/merchants` | 获取商户列表 |
| GET | `/api/properties` | 获取物业列表 |
| GET | `/api/owners/by_property/<property_id>` | 获取指定物业的业主列表 |
| GET | `/api/thresholds/<property_id>` | 查询物业积分阈值 |

### 管理员专用接口（Token 认证）

#### 认证相关

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/admin/auth/login` | 管理员登录 |
| GET | `/api/admin/auth/me` | 获取当前管理员信息 |

#### 用户管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/users` | 获取用户列表 |

#### 积分阈值管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/admin/thresholds` | 创建积分阈值 |
| PUT | `/api/admin/thresholds/<property_id>` | 更新积分阈值 |
| DELETE | `/api/admin/thresholds/<property_id>` | 删除积分阈值 |

#### 积分操作

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/points/change` | 变更用户积分 |

## 📦 数据模型

### 身份类型（IdentityType）

```python
IDENTITY_CHOICES = (
    ('OWNER', '业主'),
    ('PROPERTY', '物业'),
    ('MERCHANT', '商户'),
    ('ADMIN', '管理员'),
)
```

### 用户信息（UserInfo）

- `system_id`: 系统编号（如：OWNER_001）
- `openid`: 微信 OpenID
- `identity_type`: 身份类型
- `daily_points`: 当日积分
- `total_points`: 累计积分
- `owner_property`: 所属物业（仅业主有值）

### 商户档案（MerchantProfile）

- `merchant_id`: 商户ID
- `merchant_name`: 商户名称
- `category`: 商品分类
- `banner_urls`: 轮播图（逗号分隔）
- `positive_rating_percent`: 好评率

### 物业档案（PropertyProfile）

- `property_id`: 物业ID
- `property_name`: 物业名称
- `community_name`: 社区名称

### 积分阈值（PointsThreshold）

- `property`: 关联物业
- `min_points`: 最小积分要求

## 🔧 前端 API 使用示例

### 1. 管理员登录

```typescript
import { fetchLogin } from '@/api/auth'

const { token } = await fetchLogin({
  userName: 'admin',
  password: '123456'
})
// token 会自动存入 store 并在后续请求中携带
```

### 2. 获取用户列表

```typescript
import { fetchUsersList } from '@/api/wxmini'

const { list, total } = await fetchUsersList()
console.log(`共有 ${total} 个用户`, list)
```

### 3. 创建积分阈值

```typescript
import { createThreshold } from '@/api/wxmini'

await createThreshold({
  property_id: 'PROPERTY_001',
  min_points: 100
})
// 自动显示成功提示
```

## 🎯 RESTful 规范

- **GET**：查询资源（幂等）
- **POST**：创建资源
- **PUT**：更新资源（幂等）
- **DELETE**：删除资源（幂等）

**HTTP 状态码**：
- `200`：成功
- `201`：创建成功
- `400`：请求参数错误
- `401`：未认证
- `403`：无权限
- `404`：资源不存在
- `500`：服务器错误

## 🚀 部署说明

### 环境变量配置

```bash
# 数据库配置
MYSQL_ADDRESS=localhost:3306
MYSQL_DATABASE=django_demo
MYSQL_USERNAME=root
MYSQL_PASSWORD=your_password

# Django 配置
DEBUG=False
SECRET_KEY=your-secret-key
```

### 创建管理员账号

```bash
python manage.py createsuperuser
# 输入用户名、邮箱、密码
```

### 数据库迁移

```bash
python manage.py makemigrations
python manage.py migrate
```

### 生成管理员 Token

```bash
python manage.py shell
>>> from django.contrib.auth.models import User
>>> from rest_framework.authtoken.models import Token
>>> user = User.objects.get(username='admin')
>>> token = Token.objects.create(user=user)
>>> print(token.key)
```

## 📝 注意事项

1. **OpenID 流程**：小程序通过 `wx.cloud.callContainer` 调用时，微信云托管会自动注入 `X-WX-OPENID` 请求头，后端直接读取即可，无需额外处理。

2. **Token 格式**：前端在调用管理员接口时，需要在请求头中携带 `Authorization: Token <key>`，这个格式由 Django REST framework 的 TokenAuthentication 规定。

3. **CSRF 保护**：已在 `settings.py` 中禁用 CSRF 中间件，适配前后端分离架构。

4. **跨域配置**：如需跨域访问，需添加 `django-cors-headers` 并配置 `CORS_ALLOWED_ORIGINS`。

5. **生产环境**：记得设置 `DEBUG=False`，并配置合适的 `ALLOWED_HOSTS`。

