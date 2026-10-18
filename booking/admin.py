from django.contrib import admin

# Register your models here.

from django.contrib.auth.admin import UserAdmin
from .models import User, Room, PcSetupSpec, PcSetup, Reservation

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Данные клуба', {'fields': ('role', 'avatar')}),
    )
    list_display = ('username', 'role', 'is_active', 'is_staff')
    list_filter = ('role', 'is_active')


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'room_type', 'area_size')
    list_filter = ('room_type',)


@admin.register(PcSetupSpec)
class PcSetupSpecAdmin(admin.ModelAdmin):
    list_display = ('cpu', 'gpu', 'ram', 'monitor', 'chair')


@admin.register(PcSetup)
class PcSetupAdmin(admin.ModelAdmin):
    list_display = ('pc_number', 'room', 'status', 'spec')
    list_filter = ('room', 'status')


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'pc_setup', 'start_time', 'end_time', 'status')
    list_filter = ('status', 'start_time', 'pc_setup__room')
    search_fields = ('user__username', 'pc_setup__pc_number')