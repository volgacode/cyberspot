from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    User, Place, Room, PcSetupSpec, PcSetup, Tariff, Reserve, ReservePcSetup,
)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Личные данные', {'fields': ('first_name', 'last_name', 'avatar')}),
        ('Доступ', {'fields': ('role', 'is_active')}),
        ('Даты', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': ('username', 'password1', 'password2', 'role')}),
    )
    list_display = ('username', 'first_name', 'last_name', 'role', 'is_active')
    list_filter = ('role', 'is_active')


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_display = ('name', 'area', 'description')


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'place', 'area', 'description')
    list_filter = ('place',)


@admin.register(PcSetupSpec)
class PcSetupSpecAdmin(admin.ModelAdmin):
    list_display = ('cpu', 'gpu', 'ram', 'monitor', 'chair')


@admin.register(PcSetup)
class PcSetupAdmin(admin.ModelAdmin):
    list_display = ('pc_number', 'room', 'status', 'spec', 'pos_x', 'pos_y')
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