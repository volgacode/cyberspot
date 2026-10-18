from django.db import models

# Create your models here.

from datetime import timedelta
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.utils import timezone

class User(AbstractUser):
    class Role(models.TextChoices):
        CLIENT = 'client', 'Клиент'
        ADMIN = 'admin', 'Администратор'

    REQUIRED_FIELDS = []

    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True, verbose_name="Аватар")
    role = models.CharField(
        max_length=45, 
        choices=Role.choices, 
        default=Role.CLIENT,
        verbose_name="Роль"
    )

    @property
    def is_club_admin(self):
        return self.role == self.Role.ADMIN or self.is_staff or self.is_superuser

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

class Room(models.Model):
    name = models.CharField(max_length=45, verbose_name="Название комнаты/зоны")
    view = models.ImageField(upload_to='rooms/', null=True, blank=True, verbose_name="Фото/Вид")
    description = models.CharField(max_length=255, null=True, blank=True, verbose_name="Описание")
    area_size = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Площадь (м²)")

    class Meta:
        verbose_name = "Комната / Зона"
        verbose_name_plural = "Комнаты / Зоны"

    def __str__(self):
        return self.name

class PcSetupSpec(models.Model):
    cpu = models.CharField(max_length=45, null=True, blank=True, verbose_name="Процессор")
    gpu = models.CharField(max_length=45, null=True, blank=True, verbose_name="Видеокарта")
    ram = models.CharField(max_length=45, null=True, blank=True, verbose_name="ОЗУ")
    monitor = models.CharField(max_length=45, null=True, blank=True, verbose_name="Монитор")
    mouse = models.CharField(max_length=45, null=True, blank=True, verbose_name="Мышь")
    keyboard = models.CharField(max_length=45, null=True, blank=True, verbose_name="Клавиатура")
    headphones = models.CharField(max_length=45, null=True, blank=True, verbose_name="Наушники")
    chair = models.CharField(max_length=45, null=True, blank=True, verbose_name="Кресло")

    class Meta:
        verbose_name = "Характеристика ПК"
        verbose_name_plural = "Характеристики ПК"

    def __str__(self):
        return f"{self.cpu or 'No CPU'} | {self.gpu or 'No GPU'} | {self.ram or 'No RAM'}"

class PcSetup(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = 'available', 'Доступен'
        MAINTENANCE = 'maintenance', 'На обслуживании'

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='pc_setups', verbose_name="Комната")
    spec = models.ForeignKey(PcSetupSpec, on_delete=models.RESTRICT, related_name='pc_setups', verbose_name="Характеристики")
    pc_number = models.PositiveIntegerField(verbose_name="Номер ПК")
    status = models.CharField(max_length=45, choices=Status.choices, default=Status.AVAILABLE, verbose_name="Статус")

    class Meta:
        unique_together = ('room', 'pc_number')
        verbose_name = "Игровой ПК"
        verbose_name_plural = "Игровые ПК"
        ordering = ['room', 'pc_number']

    def __str__(self):
        return f"ПК №{self.pc_number} ({self.room.name})"

class Tariff(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='tariffs', verbose_name="Зона тарифа")
    name = models.CharField(max_length=45, verbose_name="Название тарифа")
    description = models.CharField(max_length=255, null=True, blank=True, verbose_name="Описание")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена за единицу (руб.)")
    duration_minutes = models.PositiveIntegerField(verbose_name="Длительность (минут)")

    class Meta:
        verbose_name = "Тариф"
        verbose_name_plural = "Тарифы"

    def __str__(self):
        return f"{self.name} [{self.room.name}] ({self.duration_minutes} мин. — {self.unit_price} ₽)"

class Reserve(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Активна'
        COMPLETED = 'completed', 'Завершена'
        CANCELLED = 'cancelled', 'Отменена'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reserves', verbose_name="Пользователь")
    final_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="Итоговая цена")
    status = models.CharField(max_length=45, choices=Status.choices, default=Status.ACTIVE, verbose_name="Статус")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Бронь (Заказ)"
        verbose_name_plural = "Брони (Заказы)"
        ordering = ['-created_at']

    def __str__(self):
        return f"Бронь #{self.id} — {self.user.username} ({self.get_status_display()})"

class ReservePcSetup(models.Model):
    MAX_DAYS_AHEAD = 7

    reserve = models.ForeignKey(Reserve, on_delete=models.CASCADE, related_name='pc_items', verbose_name="Бронь")
    pc_setup = models.ForeignKey(PcSetup, on_delete=models.RESTRICT, related_name='reserved_slots', verbose_name="ПК")
    tariff = models.ForeignKey(Tariff, on_delete=models.RESTRICT, related_name='reserved_slots', verbose_name="Тариф")
    tariff_unit_count = models.PositiveIntegerField(default=1, verbose_name="Количество единиц тарифа")
    start_time = models.DateTimeField(verbose_name="Время начала")
    end_time = models.DateTimeField(verbose_name="Время окончания")

    class Meta:
        verbose_name = "Позиция бронирования ПК"
        verbose_name_plural = "Позиции бронирования ПК"

    def clean(self):
        now = timezone.now()

        if self.pc_setup and self.tariff and self.pc_setup.room != self.tariff.room:
            raise ValidationError(
                f"Ошибка зоны: ПК №{self.pc_setup.pc_number} находится в '{self.pc_setup.room.name}', "
                f"а тариф '{self.tariff.name}' предназначен для '{self.tariff.room.name}'!"
            )

        if self.pc_setup and self.pc_setup.status == PcSetup.Status.MAINTENANCE:
            raise ValidationError("Этот компьютер сейчас находится на обслуживании.")

        if self.pk is None and self.start_time and self.start_time < (now - timedelta(minutes=5)):
            raise ValidationError("Нельзя забронировать время в прошлом.")

        if self.start_time and self.start_time > (now + timedelta(days=self.MAX_DAYS_AHEAD)):
            raise ValidationError(f"Нельзя бронировать более чем на {self.MAX_DAYS_AHEAD} дней вперед.")

        if self.pc_setup and self.start_time and self.end_time:
            overlaps = ReservePcSetup.objects.filter(
                pc_setup=self.pc_setup,
                reserve__status=Reserve.Status.ACTIVE,
                start_time__lt=self.end_time,
                end_time__gt=self.start_time
            )
            if self.pk:
                overlaps = overlaps.exclude(pk=self.pk)

            if overlaps.exists():
                raise ValidationError("Этот компьютер уже занят на выбранный промежуток времени.")

    def save(self, *args, **kwargs):
        if self.tariff and self.start_time and self.tariff_unit_count:
            total_duration = self.tariff.duration_minutes * self.tariff_unit_count
            self.end_time = self.start_time + timedelta(minutes=total_duration)

        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.pc_setup} | {self.start_time.strftime('%d.%m %H:%M')} - {self.end_time.strftime('%H:%M')}"