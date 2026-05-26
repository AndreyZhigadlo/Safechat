#!/bin/bash
# SafeChat — скрипт автоустановки на Ubuntu (Oracle Cloud)
set -e

echo "=== SafeChat Setup ==="

# Обновление системы
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv git

# Клонирование репозитория
cd /home/ubuntu
if [ -d "Safechat" ]; then
    echo "Обновление репозитория..."
    cd Safechat && git pull origin main
else
    echo "Клонирование репозитория..."
    git clone https://github.com/AndreyZhigadlo/Safechat.git
    cd Safechat
fi

# Виртуальное окружение
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Генерация ключей если нет .env
if [ ! -f ".env" ]; then
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    ENCRYPT_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    cat > .env << EOF
SECRET_KEY=$SECRET_KEY
ENCRYPT_KEY=$ENCRYPT_KEY
DATABASE_URL=sqlite:///messenger.db
PORT=5000
EOF
    echo "Созданы ключи в .env"
fi

# Systemd сервис
sudo tee /etc/systemd/system/safechat.service > /dev/null << 'EOF'
[Unit]
Description=SafeChat Messenger
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/Safechat
EnvironmentFile=/home/ubuntu/Safechat/.env
ExecStart=/home/ubuntu/Safechat/venv/bin/gunicorn -w 1 --threads 4 -b 0.0.0.0:5000 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable safechat
sudo systemctl restart safechat

echo ""
echo "=== Готово! ==="
echo "SafeChat запущен на порту 5000"
echo "Проверь: sudo systemctl status safechat"
