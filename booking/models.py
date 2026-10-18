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
        max_length=20, 
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

class Room(models.Model):
    class RoomType(models.TextChoices):
        STANDARD = 'standard', 'Standard'
        COMFORT = 'comfort', 'Comfort'
        VIP = 'vip', 'VIP'

    name = models.CharField(max_length=45, verbose_name="Название зоны")
    room_type = models.CharField(max_length=20, choices=RoomType.choices, verbose_name="Тип зоны")
    view = models.ImageField(upload_to='rooms/', null=True, blank=True, verbose_name="Фото/Вид зоны")
    description = models.CharField(max_length=255, blank=True, null=True, verbose_name="Описание")
    area_size = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Площадь (кв.м)")

    class Meta:
        verbose_name = "Зона (Комната)"
        verbose_name_plural = "Зоны (Комнаты)"

    def __str__(self):
        return f"{self.get_room_type_display()} — {self.name}"

class PcSetupSpec(models.Model):
    cpu = models.CharField(max_length=45, verbose_name="Процессор")
    gpu = models.CharField(max_length=45, verbose_name="Видеокарта")
    ram = models.CharField(max_length=45, verbose_name="ОЗУ")
    monitor = models.CharField(max_length=45, blank=True, null=True, verbose_name="Монитор")
    mouse = models.CharField(max_length=45, blank=True, null=True, verbose_name="Мышь")
    keyboard = models.CharField(max_length=45, blank=True, null=True, verbose_name="Клавиатура")
    headphones = models.CharField(max_length=45, blank=True, null=True, verbose_name="Наушники")
    chair = models.CharField(max_length=45, blank=True, null=True, verbose_name="Кресло")

    class Meta:
        verbose_name = "Характеристика ПК"
        verbose_name_plural = "Характеристики ПК"

    def __str__(self):
        return f"{self.cpu} / {self.gpu} / {self.ram}"

class PcSetup(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = 'available', 'Доступен'
        MAINTENANCE = 'maintenance', 'На обслуживании'

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='pcs', verbose_name="Зона")
    spec = models.ForeignKey(PcSetupSpec, on_delete=models.RESTRICT, related_name='pcs', verbose_name="Характеристики")
    pc_number = models.PositiveIntegerField(verbose_name="Номер места")
    status = models.CharField(max_length=45, choices=Status.choices, default=Status.AVAILABLE, verbose_name="Статус")

    class Meta:
        unique_together = ('room', 'pc_number')
        verbose_name = "Игровое место (ПК)"
        verbose_name_plural = "Игровые места (ПК)"
        ordering = ['room', 'pc_number']

    def __str__(self):
        return f"ПК №{self.pc_number} [{self.room.name}]"


class Reservation(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Активна'
        COMPLETED = 'completed', 'Завершена'
        CANCELLED = 'cancelled', 'Отменена'

    MAX_DAYS_AHEAD = 7

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reservations', verbose_name="Клиент")
    pc_setup = models.ForeignKey(PcSetup, on_delete=models.CASCADE, related_name='reservations', verbose_name="ПК")
    start_time = models.DateTimeField(verbose_name="Время начала")
    end_time = models.DateTimeField(verbose_name="Время окончания")
    status = models.CharField(max_length=45, choices=Status.choices, default=Status.ACTIVE, verbose_name="Статус брони")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Бронирование"
        verbose_name_plural = "Бронирования"
        ordering = ['-start_time']

    def clean(self):
        """Проверка всех бизнес-ограничений перед сохранением"""
        now = timezone.now()

        # 1. Время окончания строго позже времени начала
        if self.start_time >= self.end_time:
            raise ValidationError("Время окончания должно быть позже времени начала.")

        # 2. Нельзя бронировать задним числом (в прошлом)
        if self.pk is None and self.start_time < (now - timedelta(minutes=5)):
            raise ValidationError("Нельзя забронировать время в прошлом.")

        # 3. Не позже чем через N дней вперед
        if self.start_time > now + timedelta(days=self.MAX_DAYS_AHEAD):
            raise ValidationError(f"Нельзя бронировать более чем на {self.MAX_DAYS_AHEAD} дней вперед.")

        # 4. Проверка состояния ПК
        if self.pc_setup.status == PcSetup.Status.MAINTENANCE:
            raise ValidationError("Этот компьютер временно находится на обслуживании.")

        # 5. Проверка пересечения временных слотов (Double Booking)
        overlaps = Reservation.objects.filter(
            pc_setup=self.pc_setup,
            status=self.Status.ACTIVE,
            start_time__lt=self.end_time,
            end_time__gt=self.start_time
        )
        if self.pk:
            overlaps = overlaps.exclude(pk=self.pk)

        if overlaps.exists():
            raise ValidationError("Этот ПК уже занят на выбранный промежуток времени.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Бронь #{self.id}: {self.pc_setup} | {self.user.username} ({self.start_time.strftime('%d.%m %H:%M')})"