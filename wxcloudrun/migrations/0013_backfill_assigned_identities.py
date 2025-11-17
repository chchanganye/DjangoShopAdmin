from django.db import migrations


def forwards_backfill_assigned_identities(apps, schema_editor):
    UserInfo = apps.get_model('wxcloudrun', 'UserInfo')
    UserAssignedIdentity = apps.get_model('wxcloudrun', 'UserAssignedIdentity')
    MerchantProfile = apps.get_model('wxcloudrun', 'MerchantProfile')
    PropertyProfile = apps.get_model('wxcloudrun', 'PropertyProfile')

    # Build sets of user ids with merchant/property profiles to avoid N+1
    merchant_user_ids = set(MerchantProfile.objects.values_list('user_id', flat=True))
    property_user_ids = set(PropertyProfile.objects.values_list('user_id', flat=True))

    for u in UserInfo.objects.all():
        # Ensure OWNER assigned
        UserAssignedIdentity.objects.get_or_create(user_id=u.id, identity_type='OWNER')

        # Backfill MERCHANT assigned when merchant profile exists
        if u.id in merchant_user_ids:
            UserAssignedIdentity.objects.get_or_create(user_id=u.id, identity_type='MERCHANT')

        # Backfill PROPERTY assigned when property profile exists
        if u.id in property_user_ids:
            UserAssignedIdentity.objects.get_or_create(user_id=u.id, identity_type='PROPERTY')

        # Resolve conflicts: keep only current active_identity and OWNER
        has_merchant = UserAssignedIdentity.objects.filter(user_id=u.id, identity_type='MERCHANT').exists()
        has_property = UserAssignedIdentity.objects.filter(user_id=u.id, identity_type='PROPERTY').exists()
        if has_merchant and has_property:
            if u.active_identity == 'MERCHANT':
                UserAssignedIdentity.objects.filter(user_id=u.id, identity_type='PROPERTY').delete()
            elif u.active_identity == 'PROPERTY':
                UserAssignedIdentity.objects.filter(user_id=u.id, identity_type='MERCHANT').delete()
            else:
                UserAssignedIdentity.objects.filter(user_id=u.id, identity_type='MERCHANT').delete()
                UserAssignedIdentity.objects.filter(user_id=u.id, identity_type='PROPERTY').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('wxcloudrun', '0012_active_identity_and_assigned'),
    ]

    operations = [
        migrations.RunPython(forwards_backfill_assigned_identities, migrations.RunPython.noop),
    ]