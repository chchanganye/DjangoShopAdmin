from datetime import datetime, date

from django.db import models
from django.contrib.auth.models import User

# 已移除官方示例计数器模型 Counters（与本项目无关）


# 商品分类
class Category(models.Model):
    name = models.CharField('分类名称', max_length=100, unique=True)
    icon_file_id = models.CharField('图标文件ID', max_length=255, blank=True, default='')

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


POINTS_IDENTITY_CHOICES = (
    ('OWNER', 'OWNER'),
    ('PROPERTY', 'PROPERTY'),
    ('MERCHANT', 'MERCHANT'),
)


ORDER_STATUS_CHOICES = (
    ('PENDING_REVIEW', '待评价'),
    ('REVIEWED', '已评价'),
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
    nickname = models.CharField('用户昵称', max_length=100, blank=True, default='')
    avatar_url = models.CharField('头像云文件ID', max_length=512, blank=True, default='')  # 存储云文件ID，如：cloud://xxx.jpg
    phone_number = models.CharField('手机号', max_length=32, blank=True, default='')
    identity_type = models.CharField('身份类型(兼容字段)', max_length=20, choices=IDENTITY_CHOICES)
    active_identity = models.CharField('活跃身份', max_length=20, choices=IDENTITY_CHOICES, default='OWNER')

    daily_points = models.IntegerField('当日积分', default=0)
    total_points = models.IntegerField('累计积分', default=0)
    daily_points_date = models.DateField('当日积分日期', null=True, blank=True)  # 记录每日积分所属日期

    created_at = models.DateTimeField('创建时间', default=datetime.now)
    updated_at = models.DateTimeField('更新时间', default=datetime.now)

    # 业主所属物业（仅当 identity_type=OWNER 时有值）
    # 先声明为可空，后续数据建立后再填充
    owner_property = models.ForeignKey('PropertyProfile', verbose_name='所属物业', null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name='owners')
    owner_community = models.ForeignKey('Community', verbose_name='所属小区', null=True, blank=True,
                                        on_delete=models.SET_NULL, related_name='community_owners')

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
            prefix = self.active_identity or self.identity_type or 'USER'
            self.system_id = _generate_seq(prefix, UserInfo, 'system_id')
        # 按需设置每日积分日期
        if self.daily_points_date is None:
            self.daily_points_date = date.today()
        self.updated_at = datetime.now()
        super().save(*args, **kwargs)


# 物业档案（身份为物业）
class UserPointsAccount(models.Model):
    """用户按身份的独立积分账户（OWNER/MERCHANT/PROPERTY 互不影响）"""

    user = models.ForeignKey(
        UserInfo,
        verbose_name='关联用户',
        on_delete=models.CASCADE,
        related_name='points_accounts',
    )
    identity_type = models.CharField('积分身份', max_length=20, choices=POINTS_IDENTITY_CHOICES)

    daily_points = models.IntegerField('当日积分', default=0)
    total_points = models.IntegerField('累计积分', default=0)
    daily_points_date = models.DateField('当日积分日期', null=True, blank=True)

    created_at = models.DateTimeField('创建时间', default=datetime.now)
    updated_at = models.DateTimeField('更新时间', default=datetime.now)

    class Meta:
        db_table = 'UserPointsAccount'
        unique_together = ('user', 'identity_type')
        indexes = [
            models.Index(fields=['user', 'identity_type']),
        ]
        verbose_name = '用户积分账户'
        verbose_name_plural = '用户积分账户'

    def save(self, *args, **kwargs):
        if self.daily_points_date is None:
            self.daily_points_date = date.today()
        self.updated_at = datetime.now()
        super().save(*args, **kwargs)


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


class Community(models.Model):
    """小区信息（同一物业下可维护多个小区）"""

    property = models.ForeignKey(PropertyProfile, verbose_name='所属物业', on_delete=models.CASCADE, related_name='communities')
    community_id = models.CharField('小区ID', max_length=32, unique=True)
    community_name = models.CharField('小区名称', max_length=200)

    created_at = models.DateTimeField('创建时间', default=datetime.now)
    updated_at = models.DateTimeField('更新时间', default=datetime.now)

    class Meta:
        db_table = 'Community'
        indexes = [
            models.Index(fields=['community_id']),
            models.Index(fields=['property']),
            models.Index(fields=['community_name']),
        ]
        verbose_name = '小区信息'
        verbose_name_plural = '小区信息'

    def __str__(self):
        return f"{self.community_name}({self.community_id})"

    def save(self, *args, **kwargs):
        if not self.community_id:
            self.community_id = _generate_seq('COMMUNITY', Community, 'community_id')
        self.updated_at = datetime.now()
        super().save(*args, **kwargs)


# 商户档案（身份为商户）
class MerchantProfile(models.Model):
    user = models.OneToOneField(UserInfo, verbose_name='关联用户', on_delete=models.CASCADE, related_name='merchant_profile')
    merchant_id = models.CharField('商户ID', max_length=32, unique=True)
    merchant_name = models.CharField('商户名称', max_length=200)
    title = models.CharField('标题', max_length=200, blank=True, default='')  # 展示标题
    description = models.TextField('简介', blank=True, default='')
    banner_url = models.CharField('横幅展示图云文件ID', max_length=255, blank=True, default='')  # 存储单张图片的云文件ID，如：cloud://xxx.jpg
    contract_file_id = models.CharField('商户合同云文件ID', max_length=255, blank=True, default='')
    business_license_file_id = models.CharField('营业执照云文件ID', max_length=255, blank=True, default='')
    category = models.ForeignKey(Category, verbose_name='分类', null=True, blank=True, on_delete=models.SET_NULL)
    contact_phone = models.CharField('联系电话', max_length=32, blank=True, default='')
    address = models.CharField('地址', max_length=300, blank=True, default='')
    latitude = models.DecimalField('纬度', max_digits=10, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField('经度', max_digits=10, decimal_places=6, null=True, blank=True)
    positive_rating_percent = models.IntegerField('好评率(%)', default=0)  # 0-100
    open_hours = models.CharField('营业时间', max_length=255, blank=True, default='')
    gallery = models.JSONField('图集', default=list, blank=True)
    rating_count = models.PositiveIntegerField('评分次数', default=0)
    avg_score = models.DecimalField('平均评分', max_digits=3, decimal_places=1, default=0)

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


class RecommendedMerchant(models.Model):
    """首页推荐商户（用于小程序“推荐”分类展示）"""

    merchant = models.OneToOneField(
        MerchantProfile,
        verbose_name='商户',
        on_delete=models.CASCADE,
        related_name='recommended_entry',
    )
    sort_order = models.PositiveIntegerField('排序', default=1)

    created_at = models.DateTimeField('创建时间', default=datetime.now)
    updated_at = models.DateTimeField('更新时间', default=datetime.now)

    class Meta:
        db_table = 'RecommendedMerchant'
        indexes = [
            models.Index(fields=['sort_order'], name='RecommendedMerchant_sort_idx'),
        ]
        verbose_name = '推荐商户'
        verbose_name_plural = '推荐商户'

    def __str__(self):
        return f"{self.merchant.merchant_name}({self.sort_order})"

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        super().save(*args, **kwargs)


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
    identity_type = models.CharField('积分身份', max_length=20, choices=POINTS_IDENTITY_CHOICES, default='OWNER')
    change = models.IntegerField('积分变动值')  # 正负积分变动
    daily_points = models.IntegerField('当日积分', default=0)
    total_points = models.IntegerField('累计积分', default=0)
    source_type = models.CharField('积分来源', max_length=50, blank=True, default='')
    source_meta = models.JSONField('来源详情', blank=True, default=dict)
    created_at = models.DateTimeField('创建时间', default=datetime.now)

    class Meta:
        db_table = 'PointsRecord'
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['user', 'identity_type']),
            models.Index(fields=['created_at'], name='PointsRecord_created_at_idx'),
        ]
        verbose_name = '积分记录'
        verbose_name_plural = '积分记录'


class SettlementOrder(models.Model):
    """商户订单结算记录（用于业主评价与后台对账）"""

    order_id = models.CharField('订单ID', max_length=32, unique=True)
    merchant = models.ForeignKey(
        MerchantProfile,
        verbose_name='商户',
        on_delete=models.CASCADE,
        related_name='settlement_orders',
    )
    owner = models.ForeignKey(
        UserInfo,
        verbose_name='业主用户',
        on_delete=models.CASCADE,
        related_name='settlement_orders',
    )

    amount = models.DecimalField('订单金额', max_digits=10, decimal_places=2, default=0)
    amount_int = models.IntegerField('结算金额(取整)', default=0)

    merchant_points = models.IntegerField('商户积分', default=0)
    owner_points = models.IntegerField('业主积分', default=0)
    owner_rate = models.PositiveIntegerField('业主奖励比例(%)', default=0)

    status = models.CharField('订单状态', max_length=20, choices=ORDER_STATUS_CHOICES, default='PENDING_REVIEW')
    reviewed_at = models.DateTimeField('评价时间', null=True, blank=True)

    created_at = models.DateTimeField('创建时间', default=datetime.now)
    updated_at = models.DateTimeField('更新时间', default=datetime.now)

    class Meta:
        db_table = 'SettlementOrder'
        indexes = [
            models.Index(fields=['order_id']),
            models.Index(fields=['merchant']),
            models.Index(fields=['owner']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = '订单结算记录'
        verbose_name_plural = '订单结算记录'

    def __str__(self):
        return f"{self.order_id}({self.status})"

    def save(self, *args, **kwargs):
        if not self.order_id:
            self.order_id = _generate_seq('ORDER', SettlementOrder, 'order_id', width=6)
        self.updated_at = datetime.now()
        super().save(*args, **kwargs)


class MerchantReview(models.Model):
    """业主对商户的评价（仅允许对已结算订单评价）"""

    order = models.OneToOneField(
        SettlementOrder,
        verbose_name='订单',
        on_delete=models.CASCADE,
        related_name='review',
    )
    merchant = models.ForeignKey(
        MerchantProfile,
        verbose_name='商户',
        on_delete=models.CASCADE,
        related_name='reviews',
    )
    owner = models.ForeignKey(
        UserInfo,
        verbose_name='业主用户',
        on_delete=models.CASCADE,
        related_name='merchant_reviews',
    )
    rating = models.PositiveIntegerField('评分(1-5)', default=5)
    content = models.CharField('评价内容', max_length=500, blank=True, default='')

    created_at = models.DateTimeField('创建时间', default=datetime.now)

    class Meta:
        db_table = 'MerchantReview'
        indexes = [
            models.Index(fields=['merchant']),
            models.Index(fields=['owner']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = '商户评价'
        verbose_name_plural = '商户评价'

    def __str__(self):
        return f"{self.merchant.merchant_name}({self.rating}★)"


class PointsShareSetting(models.Model):
    """积分分成配置（全局仅一条记录）"""

    # 说明：
    # - 当前规则：商户积分 = 消费金额（1:1，小数抹掉）
    # - 该配置用于控制“业主额外奖励积分比例(%)”
    merchant_rate = models.PositiveIntegerField('业主奖励比例(%)', default=5)
    created_at = models.DateTimeField('创建时间', default=datetime.now)
    updated_at = models.DateTimeField('更新时间', default=datetime.now)

    class Meta:
        db_table = 'PointsShareSetting'
        verbose_name = '积分分成配置'
        verbose_name_plural = '积分分成配置'

    def save(self, *args, **kwargs):
        if self.merchant_rate < 0 or self.merchant_rate > 100:
            raise ValueError('业主奖励比例必须在 0-100 之间')
        self.updated_at = datetime.now()
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(id=1, defaults={'merchant_rate': 5})
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


class UserAssignedIdentity(models.Model):
    user = models.ForeignKey(UserInfo, verbose_name='用户', on_delete=models.CASCADE, related_name='assigned_identities')
    identity_type = models.CharField('身份类型', max_length=20, choices=IDENTITY_CHOICES)
    created_at = models.DateTimeField('创建时间', default=datetime.now)

    class Meta:
        db_table = 'UserAssignedIdentity'
        unique_together = ('user', 'identity_type')
        indexes = [
            models.Index(fields=['user', 'identity_type']),
        ]
        verbose_name = '用户赋予身份'
        verbose_name_plural = '用户赋予身份'


class ContactSetting(models.Model):
    """联系我们配置（全局单条）"""

    title = models.CharField('标题', max_length=200, blank=True, default='')
    content = models.TextField('文案', blank=True, default='')

    created_at = models.DateTimeField('创建时间', default=datetime.now)
    updated_at = models.DateTimeField('更新时间', default=datetime.now)

    class Meta:
        db_table = 'ContactSetting'
        verbose_name = '联系我们配置'
        verbose_name_plural = '联系我们配置'

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(id=1, defaults={'title': '联系我们', 'content': ''})
        return obj


class UserFeedback(models.Model):
    """用户意见反馈"""

    user = models.ForeignKey(UserInfo, verbose_name='用户', on_delete=models.CASCADE, related_name='feedbacks')
    content = models.TextField('反馈内容', default='')
    images = models.JSONField('图片', default=list, blank=True)

    created_at = models.DateTimeField('创建时间', default=datetime.now)
    updated_at = models.DateTimeField('更新时间', default=datetime.now)

    class Meta:
        db_table = 'UserFeedback'
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = '意见反馈'
        verbose_name_plural = '意见反馈'

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        super().save(*args, **kwargs)



# 协议合同配置（全局单条）
class ContractSetting(models.Model):
    contract_file_id = models.CharField('协议合同云文件ID', max_length=255, blank=True, default='')
    created_at = models.DateTimeField('创建时间', default=datetime.now)
    updated_at = models.DateTimeField('更新时间', default=datetime.now)

    class Meta:
        db_table = 'ContractSetting'
        verbose_name = '协议合同配置'
        verbose_name_plural = '协议合同配置'

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(id=1, defaults={'contract_file_id': ''})
        return obj


# 身份申请记录
class IdentityApplication(models.Model):
    """用户申请变更身份的记录"""
    
    STATUS_CHOICES = (
        ('PENDING', '待审核'),
        ('APPROVED', '已批准'),
        ('REJECTED', '已拒绝'),
    )
    
    user = models.ForeignKey(UserInfo, verbose_name='申请用户', on_delete=models.CASCADE, related_name='identity_applications')
    requested_identity = models.CharField('申请身份', max_length=20, choices=IDENTITY_CHOICES)
    status = models.CharField('审核状态', max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    # 业主申请需填写的物业信息
    owner_property_id = models.CharField('申请的物业ID', max_length=32, blank=True, default='')
    
    # 商户申请需填写的信息
    merchant_name = models.CharField('商户名称', max_length=200, blank=True, default='')
    merchant_description = models.TextField('商户简介', blank=True, default='')
    merchant_address = models.CharField('商户地址', max_length=300, blank=True, default='')
    merchant_phone = models.CharField('商户联系电话', max_length=32, blank=True, default='')
    
    # 物业申请需填写的信息
    property_name = models.CharField('物业名称', max_length=200, blank=True, default='')
    property_community = models.CharField('社区名称', max_length=200, blank=True, default='')
    
    # 审核信息
    reviewed_by = models.ForeignKey(User, verbose_name='审核人', null=True, blank=True, on_delete=models.SET_NULL, related_name='reviewed_applications')
    reviewed_at = models.DateTimeField('审核时间', null=True, blank=True)
    reject_reason = models.TextField('拒绝原因', blank=True, default='')
    
    created_at = models.DateTimeField('申请时间', default=datetime.now)
    updated_at = models.DateTimeField('更新时间', default=datetime.now)
    
    class Meta:
        db_table = 'IdentityApplication'
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]
        verbose_name = '身份申请'
        verbose_name_plural = '身份申请'
    
    def __str__(self):
        return f"{self.user.openid} 申请 {self.get_requested_identity_display()} - {self.get_status_display()}"
    
    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        super().save(*args, **kwargs)


# 访问统计（用于统计登录/访问次数）
class AccessLog(models.Model):
    """记录用户访问/登录日志，用于统计访问量"""
    
    openid = models.CharField('用户OpenID', max_length=128, db_index=True)
    access_date = models.DateField('访问日期', default=date.today, db_index=True)
    access_count = models.IntegerField('当日访问次数', default=1)
    first_access_at = models.DateTimeField('首次访问时间', default=datetime.now)
    last_access_at = models.DateTimeField('最后访问时间', default=datetime.now)
    
    class Meta:
        db_table = 'AccessLog'
        unique_together = [('openid', 'access_date')]  # 每个用户每天一条记录
        indexes = [
            models.Index(fields=['access_date']),
            models.Index(fields=['openid', 'access_date']),
        ]
        verbose_name = '访问日志'
        verbose_name_plural = '访问日志'
    
    def __str__(self):
        return f"{self.openid} - {self.access_date} ({self.access_count}次)"


# 用户合同签名记录（按合同版本快照）
class UserContractSignature(models.Model):
    user = models.ForeignKey(UserInfo, verbose_name='用户', on_delete=models.CASCADE, related_name='contract_signatures')
    contract_file_id = models.CharField('签署时的合同云文件ID', max_length=255)
    signature_file_id = models.CharField('签名云文件ID', max_length=255, blank=True, default='')
    signed_at = models.DateTimeField('签署时间', default=datetime.now)
    updated_at = models.DateTimeField('更新时间', default=datetime.now)

    class Meta:
        db_table = 'UserContractSignature'
        unique_together = ('user', 'contract_file_id')
        indexes = [
            models.Index(fields=['user', 'contract_file_id']),
        ]
        verbose_name = '用户合同签名'
        verbose_name_plural = '用户合同签名'

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        super().save(*args, **kwargs)
