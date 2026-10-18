from django.contrib import admin

# Register your models here.

from django.contrib.auth.admin import UserAdmin
from .models import User, Room, PcSetupSpec, PcSetup, Tariff, Reserve, ReservePcSetup

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Данные клуба', {'fields': ('role', 'avatar')}),
    )
    list_display = ('username', 'first_name', 'last_name', 'role', 'is_active', 'is_staff')
    list_filter = ('role', 'is_active')


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'area_size', 'description')


@admin.register(PcSetupSpec)
class PcSetupSpecAdmin(admin.ModelAdmin):
    list_display = ('cpu', 'gpu', 'ram', 'monitor', 'chair')


@admin.register(PcSetup)
class PcSetupAdmin(admin.ModelAdmin):
    list_display = ('pc_number', 'room', 'status', 'spec')
    list_filter = ('room', 'status')


@admin.register(Tariff)
class TariffAdmin(admin.ModelAdmin):
    list_display = ('name', 'room', 'unit_price', 'duration_minutes')
    list_filter = ('room',)


class ReservePcSetupInline(admin.TabularInline):
    model = ReservePcSetup
    extra = 1
    fields = ('pc_setup', 'tariff', 'tariff_unit_count', 'start_time', 'end_time')
    readonly_fields = ('end_time',)


@admin.register(Reserve)
class ReserveAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'final_price', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    inlines = [ReservePcSetupInline]