
# Register your models here.
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, StaffApplication

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