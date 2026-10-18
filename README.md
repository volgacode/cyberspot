# 🎮 CyberSpot — Сервис бронирования компьютерного клуба

Веб-приложение на **Python (Django)** и **MySQL** для управления бронированием игровых мест, ПК и зон в компьютерном клубе.

---

## 📋 Предварительные требования

Перед началом работы убедитесь, что на вашем компьютере установлены:
* **Python 3.10+** ([скачать с официального сайта](https://www.python.org/downloads/))
* **Git** ([скачать](https://git-scm.com/))
* **MySQL Server** (версии 8.0+) с запущенной системной службой.

---

## 🚀 Пошаговая инструкция по развертыванию с нуля

### 1. Клонирование репозитория
Откройте терминал (Git Bash / PowerShell / Linux-терминал) и выполните:
```bash
git clone https://github.com/volgacode/cyberspot.git
cd cyberspot
```

---

### 2. Создание и активация виртуального окружения

* **Создание окружения:**
  ```bash
  python -m venv venv
  ```

* **Активация окружения:**
  * **Windows (Git Bash):**
    ```bash
    source venv/Scripts/activate
    ```
    *Выйти из окружения при необходимости:*
    ```bash
    deactivate
    ```
  * **Windows (PowerShell):**
    ```powershell
    .\venv\Scripts\Activate.ps1
    ```
    *(Если появляется ошибка выполнения скриптов, выполните один раз: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`)*
  * **macOS / Linux:**
    ```bash
    source venv/bin/activate
    ```

---

### 3. Установка зависимостей
Убедитесь, что окружение активно (в начале строки терминала отображается `(venv)`):
```bash
pip install -r requirements.txt
```

---

### 4. Создание базы данных через консоль MySQL

Создайте пустую базу данных одной командой в терминале:
```bash
"/c/Program Files/MySQL/MySQL Server 8.0/bin/mysql.exe" -u root -p -e "CREATE DATABASE IF NOT EXISTS cyberspot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```
*(При запросе `Enter password:` введите пароль от вашего локального пользователя root).*

---

### 5. Настройка переменных окружения (`.env`)

Создайте в корне проекта (рядом с файлом `manage.py`) файл с именем **`.env`** и укажите данные для подключения:

```env
SECRET_KEY=django-insecure-ваш-уникальный-ключ-проекта
DEBUG=True

# Настройки подключения к MySQL
DB_NAME=cyberspot
DB_USER=root
DB_PASSWORD=ваш_пароль_от_mysql
DB_HOST=127.0.0.1
DB_PORT=3306
```

---

### 6. Развертывание базы данных и данных

Выберите один из двух вариантов в зависимости от задачи:

#### Вариант А: Быстрый запуск из готового SQL-дампа (Рекомендуется для команды)
Если в репозитории уже есть файл дампа `cyberspot_dump.sql`, разверните все таблицы и готовые данные одной командой:
```bash
"/c/Program Files/MySQL/MySQL Server 8.0/bin/mysql.exe" -u root -p cyberspot < cyberspot_dump.sql
```

#### Вариант Б: Создание таблиц с нуля через миграции Django
Если вы создаете чистую базу без готового дампа:
1. Создание файлов миграций:
   ```bash
   python manage.py makemigrations booking
   ```
2. Применение миграций:
   ```bash
   python manage.py migrate
   ```

---

### 7. Создание администратора клуба

Создайте учетную запись суперпользователя для доступа к панели управления:
```bash
python manage.py createsuperuser
```
*Введите логин и пароль (поле email можно пропустить, нажав `Enter`).*

---

### 8. Проверка и запуск сервера

Выполните системную проверку и запустите локальный сервер разработки:
```bash
python manage.py check
python manage.py runserver
```

---

## 💾 Резервное копирование и перенос базы (Бэкапы через консоль)

### Экспорт базы данных (Создание дампа)
Чтобы выгрузить актуальное состояние всей базы (структуру и данные) в файл `cyberspot_dump.sql`:

```bash
"/c/Program Files/MySQL/MySQL Workbench 8.0/mysqldump.exe" -u root -p --default-character-set=utf8mb4 cyberspot > cyberspot_dump.sql
```
*(Созданный файл `cyberspot_dump.sql` можно закоммитить в Git для передачи тиммейту).*

### Импорт базы данных (Восстановление из дампа)
Чтобы восстановить базу из существующего файла дампа:

1. Убедитесь, что база создана (см. **Шаг 4**).
2. Выполните импорт:
   ```bash
   mysql -u root -p cyberspot < cyberspot_dump.sql
   ```

> 💡 **Примечание для Windows:**  
> Если консоль пишет `command not found` для `mysql` или `mysqldump`, указывайте полный путь к утилитам в кавычках (например: `"/c/Program Files/MySQL/MySQL Server 8.0/bin/mysqldump.exe"`), либо добавьте папку `bin` вашего MySQL в системную переменную `PATH`.

---

## 🌐 Ссылки для работы

После запуска локального сервера:
* **Панель администратора:** [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)  
  *(используйте логин и пароль администратора, созданного на Шаге 7)*.

---

## 🛠 Частые проблемы и их решение

| Ошибка | Причина | Решение через консоль |
| :--- | :--- | :--- |
| **`OperationalError (1049, "Unknown database 'cyberspot'")`** | База данных еще не создана на сервере MySQL | Выполните команду создания базы из **Шага 4** |
| **`OperationalError (1045, "Access denied...")`** | Неверный логин или пароль к MySQL | Проверьте значения `DB_USER` и `DB_PASSWORD` в файле `.env` |
| **Ошибки скриптов активации в PowerShell** | Политика безопасности Windows блокирует запуск `.ps1` | В PowerShell от администратора выполните: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| **`bash: mysql: command not found`** | Утилиты MySQL не прописаны в системном `PATH` | Запускайте утилиту по полному пути: `"/c/Program Files/MySQL/MySQL Server 8.0/bin/mysql.exe"` |