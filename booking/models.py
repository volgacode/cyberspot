from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import DecimalField, ExpressionWrapper, F, Min, Q, Sum
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from .geometry import (
    bounding_box, point_in_polygon, points_are_valid, polygon_area, validate_points,
)


class User(AbstractUser):
    """
    Клиент, администратор или суперпользователь. Источник правды — поле role.
    Флаги Django is_superuser и is_staff (нужны для /admin/ и createsuperuser)
    выставляются в save() автоматически из роли.
    """

    class Role(models.TextChoices):
        CLIENT = 'client', 'Клиент'
        ADMIN = 'admin', 'Администратор'
        SUPERUSER = 'superuser', 'Суперпользователь'

    id = models.AutoField(primary_key=True, db_column='id_account')
    avatar = models.ImageField(
        'Аватар', upload_to='avatars/', max_length=128, null=True, blank=True,
    )
    role = models.CharField(
        'Роль', max_length=45, choices=Role.choices, default=Role.CLIENT,
    )

    REQUIRED_FIELDS = []

    class Meta:
        db_table = 'account'
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    @property
    def is_club_admin(self):
        """Админ клуба или суперпользователь (доступ к разделу персонала)."""
        return self.role in (self.Role.ADMIN, self.Role.SUPERUSER)

    @property
    def is_super(self):
        return self.role == self.Role.SUPERUSER

    def save(self, *args, **kwargs):
        # createsuperuser создаёт запись с is_superuser=True и ролью по умолчанию
        if self._state.adding and self.is_superuser:
            self.role = self.Role.SUPERUSER
        self.is_superuser = self.is_staff = (self.role == self.Role.SUPERUSER)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.username} ({self.get_role_display()})'


class PointsMixin:
    """Общие вычисляемые свойства для моделей с многоугольником на плане."""

    points_field = None

    @property
    def points(self):
        return getattr(self, self.points_field) or []

    @property
    def has_shape(self):
        return bool(self.points) and points_are_valid(self.points)

    @property
    def area_cells(self):
        """Площадь в клетках сетки (формула Гаусса)."""
        return polygon_area(self.points) if self.has_shape else None

    @property
    def area(self):
        """Площадь в м²: клетки² × (размер клетки в метрах)²."""
        cells = self.area_cells
        if cells is None:
            return None
        size = getattr(settings, 'PLAN_CELL_METERS', 1.0)
        return round(cells * size * size, 2)

    @property
    def bbox(self):
        """(min_x, min_y, max_x, max_y) или None."""
        return bounding_box(self.points) if self.has_shape else None


class Place(PointsMixin, models.Model):
    """Помещение клуба целиком: его контур на плане. Содержит комнаты (зоны)."""

    points_field = 'place_points'

    id = models.AutoField(primary_key=True, db_column='id_place')
    name = models.CharField('Название', max_length=45)
    view = models.ImageField(
        'Фото помещения', upload_to='places/', max_length=128, null=True, blank=True,
    )
    description = models.CharField('Описание', max_length=255, blank=True)
    place_points = models.JSONField(
        'Контур помещения', null=True, blank=True, validators=[validate_points],
        help_text='Вершины [[x, y], ...] в клетках сетки.',
    )

    class Meta:
        db_table = 'place'
        verbose_name = 'Помещение'
        verbose_name_plural = 'Помещения'

    def __str__(self):
        return self.name


class Room(PointsMixin, models.Model):
    """Комната (зона клуба: standard, comfort, vip). Зона соответствует классу мест."""

    points_field = 'room_points'

    id = models.AutoField(primary_key=True, db_column='id_room')
    place = models.ForeignKey(
        Place, on_delete=models.PROTECT, db_column='id_place',
        related_name='rooms', verbose_name='Помещение',
    )
    name = models.CharField('Название зоны', max_length=45)
    view = models.ImageField(
        'Фото зоны', upload_to='rooms/', max_length=128, null=True, blank=True,
    )
    description = models.CharField('Описание', max_length=255, blank=True)
    room_points = models.JSONField(
        'Контур комнаты', null=True, blank=True, validators=[validate_points],
        help_text='Вершины [[x, y], ...] в клетках сетки. Пусто — комната ещё не нарисована.',
    )

    class Meta:
        db_table = 'room'
        verbose_name = 'Зона'
        verbose_name_plural = 'Зоны'
        constraints = [
            models.UniqueConstraint(fields=['place', 'name'], name='uniq_room_name_in_place'),
        ]

    def clean(self):
        if self.room_points and points_are_valid(self.room_points) and self.place_id:
            outline = self.place.place_points
            if outline and points_are_valid(outline):
                if any(not point_in_polygon(x, y, outline) for x, y in self.room_points):
                    raise ValidationError(
                        {'room_points': 'Комната выходит за контур помещения.'}
                    )

    def __str__(self):
        return self.name


class PcSetupSpec(models.Model):
    """Характеристики комплекта: железо и периферия."""

    id = models.AutoField(primary_key=True, db_column='id_pc_setup_spec')
    cpu = models.CharField('Процессор', max_length=45)
    gpu = models.CharField('Видеокарта', max_length=45)
    ram = models.CharField('ОЗУ', max_length=45)
    monitor = models.CharField('Монитор', max_length=45)
    mouse = models.CharField('Мышь', max_length=45, blank=True)
    keyboard = models.CharField('Клавиатура', max_length=45, blank=True)
    headphones = models.CharField('Наушники', max_length=45, blank=True)
    chair = models.CharField('Кресло', max_length=45, blank=True)

    class Meta:
        db_table = 'pc_setup_spec'
        verbose_name = 'Характеристики ПК'
        verbose_name_plural = 'Характеристики ПК'

    def __str__(self):
        return f'{self.cpu} | {self.gpu} | {self.ram}'


class PcSetup(models.Model):
    """Конкретное игровое место. На плане рисуется квадратом со скруглёнными углами."""

    class Status(models.TextChoices):
        AVAILABLE = 'available', 'Доступен'
        MAINTENANCE = 'maintenance', 'На обслуживании'

    id = models.AutoField(primary_key=True, db_column='id_pc_setup')
    room = models.ForeignKey(
        Room, on_delete=models.PROTECT, db_column='id_room',
        related_name='pc_setups', verbose_name='Зона',
    )
    spec = models.ForeignKey(
        PcSetupSpec, on_delete=models.PROTECT, db_column='id_pc_setup_spec',
        related_name='pc_setups', verbose_name='Характеристики',
    )
    pc_number = models.PositiveIntegerField(
        'Номер ПК', db_column='pc_setup_number', validators=[MinValueValidator(1)],
        help_text='Сквозной номер в пределах помещения (клуба).',
    )
    status = models.CharField(
        'Статус', max_length=45, choices=Status.choices, default=Status.AVAILABLE,
    )
    pos_x = models.IntegerField(
        'X центра на плане', null=True, blank=True, validators=[MinValueValidator(0)],
    )
    pos_y = models.IntegerField(
        'Y центра на плане', null=True, blank=True, validators=[MinValueValidator(0)],
    )
    rotation = models.IntegerField(
        'Поворот (°)', null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(359)],
    )

    class Meta:
        db_table = 'pc_setup'
        verbose_name = 'Игровое место'
        verbose_name_plural = 'Игровые места'
        ordering = ['room', 'pc_number']
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(pos_x__isnull=True, pos_y__isnull=True)
                    | Q(pos_x__isnull=False, pos_y__isnull=False)
                ),
                name='pc_pos_both_or_none',
            ),
            models.CheckConstraint(
                condition=Q(rotation__isnull=True) | Q(rotation__gte=0, rotation__lte=359),
                name='pc_rotation_range',
            ),
        ]

    @property
    def is_placed(self):
        return self.pos_x is not None and self.pos_y is not None

    def clean(self):
        if (self.pos_x is None) != (self.pos_y is None):
            raise ValidationError('Координаты X и Y задаются вместе.')
        if self.room_id and self.pc_number:
            same = PcSetup.objects.filter(
                room__place_id=self.room.place_id, pc_number=self.pc_number,
            )
            if self.pk:
                same = same.exclude(pk=self.pk)
            if same.exists():
                raise ValidationError(
                    {'pc_number': f'ПК с номером {self.pc_number} уже есть в этом помещении.'}
                )
        if self.is_placed and self.room_id:
            shape = self.room.room_points
            if shape and points_are_valid(shape):
                if not point_in_polygon(self.pos_x, self.pos_y, shape):
                    raise ValidationError(
                        {'pos_x': 'Центр ПК должен лежать внутри контура его комнаты.'}
                    )

    def __str__(self):
        return f'ПК №{self.pc_number} · {self.room.name}'


class Tariff(models.Model):
    """Тариф зоны: цена за единицу и длительность единицы в минутах."""

    id = models.AutoField(primary_key=True, db_column='id_tariff')
    room = models.ForeignKey(
        Room, on_delete=models.PROTECT, db_column='id_room',
        related_name='tariffs', verbose_name='Зона тарифа',
    )
    name = models.CharField('Название тарифа', max_length=45)
    description = models.CharField('Описание', max_length=255, blank=True)
    unit_price = models.DecimalField(
        'Цена за единицу (₽)', max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
    )
    duration_minutes = models.PositiveIntegerField(
        'Длительность единицы (мин.)', validators=[MinValueValidator(1)],
    )

    class Meta:
        db_table = 'tariff'
        verbose_name = 'Тариф'
        verbose_name_plural = 'Тарифы'
        constraints = [
            models.UniqueConstraint(fields=['room', 'name'], name='uniq_tariff_name_in_room'),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name='tariff_price_non_negative'),
            models.CheckConstraint(condition=Q(duration_minutes__gt=0), name='tariff_duration_positive'),
        ]

    def __str__(self):
        return f'{self.name} [{self.room.name}] ({self.duration_minutes} мин. — {self.unit_price} ₽)'


class Reserve(models.Model):
    """Бронь клиента. Состоит из одного или нескольких мест (ReservePcSetup)."""

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Активна'
        CANCELLED = 'cancelled', 'Отменена'

    id = models.AutoField(primary_key=True, db_column='id_reserve')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        db_column='id_account', related_name='reserves', verbose_name='Клиент',
    )
    final_price = models.DecimalField(
        'Итоговая цена', max_digits=10, decimal_places=2,
        default=Decimal('0.00'), editable=False,
    )
    status = models.CharField(
        'Статус', max_length=45, choices=Status.choices, default=Status.ACTIVE,
    )
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)

    class Meta:
        db_table = 'reserve'
        verbose_name = 'Бронь'
        verbose_name_plural = 'Брони'
        ordering = ['-created_at']

    def __str__(self):
        owner = self.user.username if self.user else 'удалённый аккаунт'
        return f'Бронь №{self.pk} — {owner} ({self.get_status_display()})'

    def recalc_price(self):
        """Итог = сумма (цена тарифа × количество единиц) по всем местам брони."""
        total = self.pc_items.aggregate(
            total=Sum(ExpressionWrapper(
                F('tariff__unit_price') * F('tariff_unit_count'),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ))
        )['total'] or Decimal('0.00')
        Reserve.objects.filter(pk=self.pk).update(final_price=total)
        self.final_price = total
        return total

    @property
    def first_start(self):
        """Самое раннее начало среди мест брони."""
        return self.pc_items.aggregate(m=Min('start_time'))['m']

    def can_client_cancel(self, now=None):
        """Клиент может отменить активную бронь не позже чем за N минут до начала."""
        if self.status != self.Status.ACTIVE:
            return False
        first = self.first_start
        if first is None:
            return True
        now = now or timezone.now()
        return first - now >= timedelta(minutes=settings.CLIENT_CANCEL_BEFORE_MINUTES)

    def cancel(self):
        self.status = self.Status.CANCELLED
        self.save(update_fields=['status'])

    @classmethod
    def cancel_upcoming_for(cls, user):
        """Отменить все будущие брони пользователя (вызывать при блокировке). Возвращает число."""
        ids = list(
            cls.objects.filter(user=user, status=cls.Status.ACTIVE)
            .annotate(earliest=Min('pc_items__start_time'))
            .filter(earliest__gt=timezone.now())
            .values_list('pk', flat=True)
        )
        return cls.objects.filter(pk__in=ids).update(status=cls.Status.CANCELLED)


class ReservePcSetup(models.Model):
    """
    Место в брони: тариф, количество единиц, интервал времени.

    Два способа задать время (достаточно одного):
      1) начало + количество единиц тарифа -> конец считается сам;
      2) начало + конец                     -> количество единиц считается само
         (длительность должна быть кратна длительности тарифа).
    Если заданы и количество, и конец, приоритет у количества.
    """

    PAST_TOLERANCE = timedelta(minutes=5)

    id = models.AutoField(primary_key=True, db_column='id_reserve_pc')
    reserve = models.ForeignKey(
        Reserve, on_delete=models.CASCADE, db_column='id_reserve',
        related_name='pc_items', verbose_name='Бронь',
    )
    pc_setup = models.ForeignKey(
        PcSetup, on_delete=models.PROTECT, db_column='id_pc_setup',
        related_name='reserved_slots', verbose_name='ПК',
    )
    tariff = models.ForeignKey(
        Tariff, on_delete=models.PROTECT, db_column='id_tariff',
        related_name='reserved_slots', verbose_name='Тариф',
    )
    tariff_unit_count = models.PositiveIntegerField(
        'Количество единиц тарифа', blank=True,
        validators=[MinValueValidator(1)],
    )
    start_time = models.DateTimeField('Время начала')
    end_time = models.DateTimeField('Время окончания', blank=True)

    class Meta:
        db_table = 'reserve_pc_setup'
        verbose_name = 'Место в брони'
        verbose_name_plural = 'Места в брони'
        constraints = [
            models.CheckConstraint(
                condition=Q(end_time__gt=F('start_time')), name='rps_end_after_start',
            ),
            models.CheckConstraint(
                condition=Q(tariff_unit_count__gt=0), name='rps_count_positive',
            ),
        ]

    @property
    def cost(self):
        """Вычисляемое поле: цена тарифа × количество единиц."""
        return self.tariff.unit_price * (self.tariff_unit_count or 0)

    def clean(self):
        errors = {}

        def add(field, message):
            errors.setdefault(field, []).append(message)

        now = timezone.now()
        pc = self.pc_setup if self.pc_setup_id else None
        tariff = self.tariff if self.tariff_id else None

        if pc and tariff and pc.room_id != tariff.room_id:
            add('tariff',
                f'Тариф «{tariff.name}» относится к зоне «{tariff.room.name}», '
                f'а ПК №{pc.pc_number} находится в зоне «{pc.room.name}».')

        if pc and self._state.adding and pc.status == PcSetup.Status.MAINTENANCE:
            add('pc_setup', 'Этот компьютер сейчас находится на обслуживании.')

        if tariff and self.start_time:
            duration = tariff.duration_minutes
            if self.tariff_unit_count:
                self.end_time = self.start_time + timedelta(minutes=duration * self.tariff_unit_count)
            elif self.end_time:
                seconds = int((self.end_time - self.start_time).total_seconds())
                if seconds <= 0:
                    add(NON_FIELD_ERRORS, 'Конец брони должен быть позже начала.')
                else:
                    count, rest = divmod(seconds, duration * 60)
                    if rest or count == 0:
                        add(NON_FIELD_ERRORS,
                            f'Длительность должна быть кратна длительности тарифа ({duration} мин.).')
                    else:
                        self.tariff_unit_count = count
            else:
                add('tariff_unit_count',
                    'Укажите количество единиц тарифа или время окончания.')

        if self.start_time and self._state.adding:
            if self.start_time < now - self.PAST_TOLERANCE:
                add('start_time', 'Нельзя забронировать время в прошлом.')
            days = settings.MAX_BOOKING_DAYS_AHEAD
            if self.start_time > now + timedelta(days=days):
                add('start_time', f'Нельзя бронировать более чем на {days} дн. вперёд.')

        reserve_active = (
            not self.reserve_id or self.reserve.status == Reserve.Status.ACTIVE
        )
        if pc and self.start_time and self.end_time and reserve_active:
            overlaps = ReservePcSetup.objects.filter(
                pc_setup=pc,
                reserve__status=Reserve.Status.ACTIVE,
                start_time__lt=self.end_time,
                end_time__gt=self.start_time,
            )
            if self.pk:
                overlaps = overlaps.exclude(pk=self.pk)
            if overlaps.exists():
                add('pc_setup', 'Этот компьютер уже занят на выбранное время.')

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.start_time and self.end_time:
            return f'{self.pc_setup} | {self.start_time:%d.%m %H:%M} – {self.end_time:%H:%M}'
        return str(self.pc_setup)


@receiver([post_save, post_delete], sender=ReservePcSetup)
def refresh_reserve_price(sender, instance, **kwargs):
    """После любого изменения мест брони пересчитываем итоговую цену."""
    reserve = Reserve.objects.filter(pk=instance.reserve_id).first()
    if reserve:
        reserve.recalc_price()