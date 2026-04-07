
# Register your models here.
from django.contrib import admin
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
    list_display  = ['full_name', 'email', 'role_applied', 'status', 'applied_at']
    list_filter   = ['role_applied', 'status']
    search_fields = ['full_name', 'email']
    readonly_fields = ['applied_at']
    list_editable = ['status']


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
    list_display = ['recipient', 'notification_type', 'created_at', 'is_read']
    list_filter = ['notification_type', 'is_read']
    search_fields = ['recipient__username', 'message']


@admin.register(ContactOTP)
class ContactOTPAdmin(admin.ModelAdmin):
    list_display = ['purpose', 'channel', 'target', 'attempts', 'created_at', 'expires_at', 'verified_at']
    list_filter = ['purpose', 'channel', 'verified_at']
    search_fields = ['target']
    readonly_fields = ['created_at', 'last_sent_at', 'expires_at', 'verified_at']
