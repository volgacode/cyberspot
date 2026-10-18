# 🎮 CyberSpot — Сервис бронирования компьютерного клуба

Веб-приложение на **Python (Django)** и **MySQL** для управления бронированием игровых мест, ПК и зон в компьютерном клубе.

---

## 📋 Предварительные требования

Перед началом работы убедитесь, что на вашем компьютере установлены:
* **Python 3.10+** ([скачать с официального сайта](https://www.python.org/downloads/))
* **Git** ([скачать](https://git-scm.com/))
* **MySQL Server** (версии 8.0+) с запущенной службой.

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
    Выйти из venv:
    ```bash
    deactivate
    ```
  * **Windows (PowerShell):**
    ```powershell
    .\venv\Scripts\Activate.ps1
    ```
    *(Если появляется ошибка доступа скриптов, выполните один раз: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`)*
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

### 4. Создание базы данных в MySQL
Перед запуском Django необходимо создать пустую базу данных. Зайдите в **MySQL Workbench** или выполните в консоли MySQL:

```sql
CREATE DATABASE IF NOT EXISTS cyberspot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

---

### 5. Настройка переменных окружения (`.env`)

Создайте в корневой папке проекта (рядом с файлом `manage.py`) файл с именем **`.env`** и укажите данные для подключения к вашей базе данных:

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

### 6. Создание миграций, применение к базе и загрузка данных

1. **Создание файлов миграций для приложения `booking`:**
   ```bash
   python manage.py makemigrations booking
   ```

2. **Применение миграций (создание таблиц в MySQL):**
   ```bash
   python manage.py migrate
   ```

3. **Загрузка готовых тестовых данных (зоны, характеристики, компьютеры):**
   ```bash
   python manage.py loaddata initial_data.json
   ```

---

### 7. Создание администратора клуба

Создайте учетную запись администратора для входа в панель управления:
```bash
python manage.py createsuperuser
```
*Введите желаемый логин и пароль (поле email можно пропустить, просто нажав `Enter`).*

---

### 8. Проверка и запуск сервера

Выполните системную проверку и запустите сервер разработки:
```bash
python manage.py check
python manage.py runserver
```

---

## 🌐 Ссылки для работы

После запуска локального сервера:
* **Панель администратора:** [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)  
  *(используйте данные учетной записи администратора, созданной на Шаге 7)*.

---

## 🛠 Частые проблемы и их решение

| Ошибка | Причина | Решение |
| :--- | :--- | :--- |
| **`OperationalError (1049, "Unknown database 'cyberspot'")`** | База данных еще не создана на сервере MySQL | Выполните SQL-запрос из **Шага 4** в Workbench или терминале |
| **`OperationalError (1045, "Access denied...")`** | Неверный логин или пароль к MySQL | Проверьте значения `DB_USER` и `DB_PASSWORD` в файле `.env` |
| **Ошибки скриптов активации в PowerShell** | Политика безопасности Windows блокирует запуск `.ps1` | Запустите PowerShell от администратора и выполните: `Set-ExecutionPolicy RemoteSigned` |
