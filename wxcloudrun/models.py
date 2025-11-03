from datetime import datetime, date

from django.db import models

# 已移除官方示例计数器模型 Counters（与本项目无关）


# 商品分类
class Category(models.Model):
    name = models.CharField('分类名称', max_length=100, unique=True)
    icon_name = models.CharField('图标名称', max_length=100, blank=True, default='')

    created_at = models.DateTimeField('创建时间', default=datetime.now)
    updated_at = models.DateTimeField('更新时间', default=datetime.now)

    class Meta:
        db_table = 'Category'
        indexes = [
            models.Index(fields=['name']),
        ]
        verbose_name = '商品分类'
        verbose_name_plural = '商品分类'

    def __str__(self):
        return self.name


IDENTITY_CHOICES = (
    ('OWNER', '业主'),
    ('PROPERTY', '物业'),
    ('MERCHANT', '商户'),
    ('ADMIN', '管理员'),
)


def _generate_seq(prefix: str, model_cls, field_name: str, width: int = 3):
    """
    Generate a unique sequential ID with given prefix and zero-padded width.
    Ensures uniqueness by checking existing records.
    """
    base = f"{prefix}_"
    # Try sequentially from count+1 to find a free slot
    existing = (
        model_cls.objects.filter(**{f"{field_name}__startswith": base})
        .values_list(field_name, flat=True)
    )
    used_numbers = set()
    for v in existing:
        try:
            used_numbers.add(int(v.split('_')[-1]))
        except Exception:
            continue
    n = 1
    while True:
        if n not in used_numbers:
            return f"{base}{str(n).zfill(width)}"
        n += 1


# 用户信息
class UserInfo(models.Model):
    system_id = models.CharField('系统编号', max_length=32, unique=True)  # 身份前缀+序列号，如 OWNER_001
    openid = models.CharField('OpenID', max_length=128, unique=True)
    avatar_url = models.CharField('头像URL', max_length=512, blank=True, default='')
    phone_number = models.CharField('手机号', max_length=32, blank=True, default='')
    identity_type = models.CharField('身份类型', max_length=20, choices=IDENTITY_CHOICES)

    daily_points = models.IntegerField('当日积分', default=0)
    total_points = models.IntegerField('累计积分', default=0)
    daily_points_date = models.DateField('当日积分日期', null=True, blank=True)  # 记录每日积分所属日期

    created_at = models.DateTimeField('创建时间', default=datetime.now)
    updated_at = models.DateTimeField('更新时间', default=datetime.now)

    # 业主所属物业（仅当 identity_type=OWNER 时有值）
    # 先声明为可空，后续数据建立后再填充
    owner_property = models.ForeignKey('PropertyProfile', verbose_name='所属物业', null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name='owners')

    class Meta:
        db_table = 'UserInfo'
        indexes = [
            models.Index(fields=['openid']),
            models.Index(fields=['identity_type']),
        ]
        verbose_name = '用户信息'
        verbose_name_plural = '用户信息'

    def __str__(self):
        return f"{self.system_id}({self.get_identity_type_display()})"

    def save(self, *args, **kwargs):
        # 自动生成 system_id
        if not self.system_id:
            prefix = self.identity_type or 'USER'
            self.system_id = _generate_seq(prefix, UserInfo, 'system_id')
        # 按需设置每日积分日期
        if self.daily_points_date is None:
            self.daily_points_date = date.today()
        self.updated_at = datetime.now()
        super().save(*args, **kwargs)


# 物业档案（身份为物业）
class PropertyProfile(models.Model):
    user = models.OneToOneField(UserInfo, verbose_name='关联用户', on_delete=models.CASCADE, related_name='property_profile')
    property_id = models.CharField('物业ID', max_length=32, unique=True)
    property_name = models.CharField('物业名称', max_length=200)
    community_name = models.CharField('社区名称', max_length=200, blank=True, default='')

    created_at = models.DateTimeField('创建时间', default=datetime.now)
    updated_at = models.DateTimeField('更新时间', default=datetime.now)

    class Meta:
        db_table = 'PropertyProfile'
        indexes = [
            models.Index(fields=['property_id']),
        ]
        verbose_name = '物业信息'
        verbose_name_plural = '物业信息'

    def __str__(self):
        return f"{self.property_name}({self.property_id})"

    def save(self, *args, **kwargs):
        if not self.property_id:
            self.property_id = _generate_seq('PROPERTY', PropertyProfile, 'property_id')
        self.updated_at = datetime.now()
        super().save(*args, **kwargs)


# 商户档案（身份为商户）
class MerchantProfile(models.Model):
    user = models.OneToOneField(UserInfo, verbose_name='关联用户', on_delete=models.CASCADE, related_name='merchant_profile')
    merchant_id = models.CharField('商户ID', max_length=32, unique=True)
    merchant_name = models.CharField('商户名称', max_length=200)
    title = models.CharField('标题', max_length=200, blank=True, default='')  # 展示标题
    description = models.TextField('简介', blank=True, default='')
    banner_urls = models.TextField('轮播图URL(逗号分隔)', blank=True, default='')  # 逗号分隔的URL
    category = models.ForeignKey(Category, verbose_name='分类', null=True, blank=True, on_delete=models.SET_NULL)
    contact_phone = models.CharField('联系电话', max_length=32, blank=True, default='')
    address = models.CharField('地址', max_length=300, blank=True, default='')
    positive_rating_percent = models.IntegerField('好评率(%)', default=0)  # 0-100

    created_at = models.DateTimeField('创建时间', default=datetime.now)
    updated_at = models.DateTimeField('更新时间', default=datetime.now)

    class Meta:
        db_table = 'MerchantProfile'
        indexes = [
            models.Index(fields=['merchant_id']),
            models.Index(fields=['merchant_name']),
        ]
        verbose_name = '商户信息'
        verbose_name_plural = '商户信息'

    def __str__(self):
        return f"{self.merchant_name}({self.merchant_id})"

    def save(self, *args, **kwargs):
        if not self.merchant_id:
            self.merchant_id = _generate_seq('MERCHANT', MerchantProfile, 'merchant_id')
        self.updated_at = datetime.now()
        super().save(*args, **kwargs)

    def banner_list(self):
        if not self.banner_urls:
            return []
        return [s for s in self.banner_urls.split(',') if s]


# 积分阈值配置
class PointsThreshold(models.Model):
    property = models.OneToOneField(PropertyProfile, verbose_name='物业', on_delete=models.CASCADE, related_name='points_threshold')
    min_points = models.IntegerField('最小积分', default=0)

    created_at = models.DateTimeField('创建时间', default=datetime.now)
    updated_at = models.DateTimeField('更新时间', default=datetime.now)

    class Meta:
        db_table = 'PointsThreshold'
        verbose_name = '积分阈值'
        verbose_name_plural = '积分阈值'

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        super().save(*args, **kwargs)


# 积分记录（用于统计）
class PointsRecord(models.Model):
    user = models.ForeignKey(UserInfo, verbose_name='用户', on_delete=models.CASCADE, related_name='points_records')
    change = models.IntegerField('积分变动值')  # 正负积分变动
    created_at = models.DateTimeField('创建时间', default=datetime.now)

    class Meta:
        db_table = 'PointsRecord'
        indexes = [
            models.Index(fields=['user']),
        ]
        verbose_name = '积分记录'
        verbose_name_plural = '积分记录'


class PointsShareSetting(models.Model):
    """积分分成配置（全局仅一条记录）"""

    merchant_rate = models.PositiveIntegerField('商户积分比例(%)', default=90)
    created_at = models.DateTimeField('创建时间', default=datetime.now)
    updated_at = models.DateTimeField('更新时间', default=datetime.now)

    class Meta:
        db_table = 'PointsShareSetting'
        verbose_name = '积分分成配置'
        verbose_name_plural = '积分分成配置'

    def save(self, *args, **kwargs):
        if self.merchant_rate < 0 or self.merchant_rate > 100:
            raise ValueError('商户积分比例必须在 0-100 之间')
        self.updated_at = datetime.now()
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(id=1, defaults={'merchant_rate': 90})
        return obj


# 接口权限配置
class ApiPermission(models.Model):
    endpoint_name = models.CharField('接口标识', max_length=100)  # 唯一标识一个接口，如 'categories_list'
    method = models.CharField('请求方法', max_length=10, default='GET')  # GET/POST/PUT/DELETE
    allowed_identities = models.CharField('允许身份列表', max_length=200, default='OWNER,PROPERTY,MERCHANT,ADMIN')  # 逗号分隔

    created_at = models.DateTimeField('创建时间', default=datetime.now)
    updated_at = models.DateTimeField('更新时间', default=datetime.now)

    class Meta:
        db_table = 'ApiPermission'
        unique_together = ('endpoint_name', 'method')
        verbose_name = '接口权限'
        verbose_name_plural = '接口权限'

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        super().save(*args, **kwargs)

    def allowed_list(self):
        return [s for s in self.allowed_identities.split(',') if s]
