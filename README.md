# 🔐 SafeChat — Приватный мессенджер

Мессенджер с end-to-end шифрованием, автоудалением сообщений и без слежки.

## Функции
- Регистрация без телефона и email
- Шифрование всех сообщений (Fernet/AES)
- Автоудаление сообщений по таймеру
- Ручное удаление своих сообщений
- Онлайн-статус пользователей
- Работает в браузере на любом устройстве

## Деплой на Render.com

1. Загрузи проект на GitHub
2. Зайди на render.com
3. New → Web Service → подключи GitHub репозиторий
4. Настройки:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 app:app`
5. Environment Variables добавь:
   - `SECRET_KEY` = любой длинный случайный текст
   - `ENCRYPT_KEY` = запусти `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` и вставь результат
6. Нажми Deploy

## Локальный запуск
```bash
pip install -r requirements.txt
python app.py
```
Открой http://localhost:5000
