from django.contrib import admin
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.contrib.auth.admin import UserAdmin
from .models import (
    User,
    StaffApplication,
    VendorProfile,
    MenuItem,
    Order,
    OrderItem,
    Notification,
    ContactOTP,
)

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display  = ['username', 'email', 'role', 'phone', 'is_active']
    list_filter   = ['role', 'is_active']
    fieldsets     = UserAdmin.fieldsets + (
        ('Campus Info', {'fields': ('role', 'phone')}),
    )

@admin.register(StaffApplication)
class StaffApplicationAdmin(admin.ModelAdmin):
    list_display  = ['full_name', 'email', 'role_applied', 'status', 'applied_at', 'reviewed_at']
    list_filter   = ['role_applied', 'status']
    search_fields = ['full_name', 'email']
    readonly_fields = ['applied_at', 'reviewed_at', 'related_notifications']
    list_editable = ['status']
    actions = ['approve_selected_applications', 'reject_selected_applications']

    fieldsets = (
        ('Applicant', {
            'fields': ('full_name', 'email', 'phone', 'role_applied', 'status', 'admin_notes'),
        }),
        ('Documents', {
            'fields': ('aadhaar_number', 'aadhaar_document'),
        }),
        ('Vendor Details', {
            'fields': (
                'outlet_name', 'outlet_location', 'cuisine_type', 'operating_hours',
                'fssai_license', 'fssai_document', 'gst_number', 'college_noc',
                'bank_account', 'ifsc_code',
            ),
        }),
        ('Delivery Details', {
            'fields': (
                'vehicle_type', 'vehicle_number', 'driving_license',
                'driving_license_document', 'emergency_contact',
            ),
        }),
        ('Admin Tracking', {
            'fields': ('applied_at', 'reviewed_at', 'related_notifications'),
        }),
    )

    @admin.action(description='Approve selected applications')
    def approve_selected_applications(self, request, queryset):
        updated_count = 0
        for application in queryset.exclude(status=StaffApplication.Status.APPROVED):
            application.status = StaffApplication.Status.APPROVED
            application.reviewed_at = timezone.now()
            application.save(update_fields=['status', 'reviewed_at'])
            updated_count += 1
        self.message_user(request, f'Approved {updated_count} application(s).')

    @admin.action(description='Reject selected applications')
    def reject_selected_applications(self, request, queryset):
        updated_count = 0
        for application in queryset.exclude(status=StaffApplication.Status.REJECTED):
            application.status = StaffApplication.Status.REJECTED
            application.reviewed_at = timezone.now()
            application.save(update_fields=['status', 'reviewed_at'])
            updated_count += 1
        self.message_user(request, f'Rejected {updated_count} application(s).')

    def save_model(self, request, obj, form, change):
        if change and 'status' in form.changed_data and obj.status != StaffApplication.Status.PENDING:
            obj.reviewed_at = timezone.now()
        elif change and 'status' in form.changed_data and obj.status == StaffApplication.Status.PENDING:
            obj.reviewed_at = None
        super().save_model(request, obj, form, change)

    def related_notifications(self, obj):
        notifications = obj.notifications.select_related('recipient')
        if not notifications.exists():
            return 'No admin notifications yet.'

        return format_html_join(
            format_html('<br>'),
            '<a href="{}">Notification for {} ({})</a>',
            (
                (
                    reverse('admin:users_notification_change', args=[notification.pk]),
                    notification.recipient.username,
                    'read' if notification.is_read else 'unread',
                )
                for notification in notifications
            ),
        )

    related_notifications.short_description = 'Admin Notifications'


@admin.register(VendorProfile)
class VendorProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'outlet_name', 'google_maps_location', 'created_at']
    search_fields = ['user__username', 'outlet_name']


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ['vendor', 'name', 'price', 'is_active', 'updated_at']
    list_filter = ['is_active']
    search_fields = ['name', 'vendor__outlet_name']


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['order_code', 'student', 'vendor', 'vendor_decision', 'vendor_status', 'delivery_status', 'created_at']
    list_filter = ['vendor_decision', 'vendor_status', 'delivery_status']
    search_fields = ['order_code', 'student__username', 'vendor__outlet_name']
    inlines = [OrderItemInline]


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'notification_type', 'linked_object', 'created_at', 'is_read']
    list_filter = ['notification_type', 'is_read']
    search_fields = ['recipient__username', 'message']
    readonly_fields = ['linked_object']

    def linked_object(self, obj):
        if obj.application_id:
            url = reverse('admin:users_staffapplication_change', args=[obj.application_id])
            return format_html('<a href="{}">Application #{}</a>', url, obj.application_id)
        if obj.order_id:
            url = reverse('admin:users_order_change', args=[obj.order_id])
            return format_html('<a href="{}">Order {}</a>', url, obj.order.order_code or obj.order_id)
        return '-'

    linked_object.short_description = 'Linked Object'


@admin.register(ContactOTP)
class ContactOTPAdmin(admin.ModelAdmin):
    list_display = ['purpose', 'channel', 'target', 'attempts', 'created_at', 'expires_at', 'verified_at']
    list_filter = ['purpose', 'channel', 'verified_at']
    search_fields = ['target']
    readonly_fields = ['created_at', 'last_sent_at', 'expires_at', 'verified_at']
