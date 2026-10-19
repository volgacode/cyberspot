from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import DecimalField, ExpressionWrapper, F, Min, Q, Sum
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

class User(AbstractUser):
    """Клиент или администратор клуба. Суперпользователь определяется флагом is_superuser."""
 
    class Role(models.TextChoices):
        CLIENT = 'client', 'Клиент'
        ADMIN = 'admin', 'Администратор'
 
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
        return self.role == self.Role.ADMIN or self.is_superuser
 
    def __str__(self):
        return f'{self.username} ({self.get_role_display()})'
 
class Room(models.Model):
    """Зона клуба (standard, comfort, vip). Зона соответствует классу мест."""
 
    id = models.AutoField(primary_key=True, db_column='id_room')
    name = models.CharField('Название зоны', max_length=45, unique=True)
    view = models.ImageField(
        'Фото зоны', upload_to='rooms/', max_length=128, null=True, blank=True,
    )
    description = models.CharField('Описание', max_length=255, blank=True)
    area_size = models.DecimalField(
        'Площадь (м²)', max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
 
    class Meta:
        db_table = 'room'
        verbose_name = 'Зона'
        verbose_name_plural = 'Зоны'
        constraints = [
            models.CheckConstraint(condition=Q(area_size__gt=0), name='room_area_positive'),
        ]
 
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
    """Конкретное игровое место."""
 
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
        'Номер ПК', validators=[MinValueValidator(1)],
    )
    status = models.CharField(
        'Статус', max_length=45, choices=Status.choices, default=Status.AVAILABLE,
    )
 
    class Meta:
        db_table = 'pc_setup'
        verbose_name = 'Игровое место'
        verbose_name_plural = 'Игровые места'
        ordering = ['room', 'pc_number']
        constraints = [
            models.UniqueConstraint(fields=['room', 'pc_number'], name='uniq_pc_number_in_room'),
        ]
 
    def __str__(self):
        return f'ПК №{self.pc_number} ({self.room.name})'
 
 
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