from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    # аккаунт
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('account/delete/', views.delete_account, name='delete_account'),
    # клиент
    path('zones/', views.zones, name='zones'),
    path('zones/<int:room_id>/', views.zone_detail, name='zone_detail'),
    path('book/', views.book, name='book'),
    path('reserves/', views.my_reserves, name='my_reserves'),
    path('reserves/cancel/', views.cancel_reserve, name='cancel_reserve'),
    # администратор
    path('staff/reserves/', views.staff_reserves, name='staff_reserves'),
    path('staff/reserves/extend/', views.staff_extend, name='staff_extend'),
    path('staff/accounts/', views.staff_accounts, name='staff_accounts'),
    path('staff/accounts/active/', views.staff_set_active, name='staff_set_active'),
    # суперпользователь
    path('staff/accounts/role/', views.staff_set_role, name='staff_set_role'),
    path('editor/', views.editor, name='editor'),
    path('api/place/<int:place_id>/points/', views.api_place_points, name='api_place_points'),
    path('api/room/<int:room_id>/points/', views.api_room_points, name='api_room_points'),
    path('api/room/create/', views.api_room_create, name='api_room_create'),
    path('api/pc/<int:pc_id>/move/', views.api_pc_move, name='api_pc_move'),
    path('api/pc/<int:pc_id>/status/', views.api_pc_status, name='api_pc_status'),
    path('api/pc/create/', views.api_pc_create, name='api_pc_create'),
    path('api/tariff/create/', views.api_tariff_create, name='api_tariff_create'),
    path('api/spec/create/', views.api_spec_create, name='api_spec_create'),
]