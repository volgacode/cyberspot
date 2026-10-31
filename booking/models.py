"""
Django-модель нужна ТОЛЬКО для таблицы account: на ней держатся
login/logout, сессии и request.user. Все остальные таблицы
(place, room, pc_setup, tariff, reserve, ...) читаются и пишутся
чистым SQL в booking/queries.py.

Схема БД ведётся в MySQL Workbench (ER-диаграмма -> schema.sql),
поэтому managed = False: Django эту таблицу не создаёт и не меняет.
"""
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils import timezone

ROLE_LEVEL = {'client': 1, 'admin': 2, 'superuser': 3}


class UserManager(BaseUserManager):
    """get_by_natural_key приходит из BaseUserManager (нужен ModelBackend)."""

    def create_user(self, username, password, role='client', **extra):
        user = self.model(username=username, role=role, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user


class User(AbstractBaseUser):
    class Role(models.TextChoices):
        CLIENT = 'client', 'Клиент'
        ADMIN = 'admin', 'Администратор'
        SUPERUSER = 'superuser', 'Суперпользователь'

    id = models.AutoField(primary_key=True, db_column='id_account')
    username = models.CharField(max_length=150, unique=True)
    # password приходит из AbstractBaseUser (колонка `password`)
    role = models.CharField(max_length=45, choices=Role.choices, default=Role.CLIENT)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)
    avatar = models.CharField(max_length=128, null=True, blank=True)
    first_name = models.CharField(max_length=150, null=True, blank=True)
    last_name = models.CharField(max_length=150, null=True, blank=True)

    # В таблице account нет колонки last_login -> отключаем поле
    # (Django при этом сам не подключает сигнал update_last_login).
    last_login = None

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        db_table = 'account'
        managed = False

    @property
    def level(self):
        return ROLE_LEVEL.get(self.role, 0)

    @property
    def is_club_admin(self):
        """Администратор или суперпользователь."""
        return self.level >= ROLE_LEVEL['admin']

    @property
    def is_super(self):
        return self.level >= ROLE_LEVEL['superuser']

    def __str__(self):
        return f'{self.username} ({self.get_role_display()})'