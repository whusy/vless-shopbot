#!/bin/bash

# ==============================================================================
# Установочный скрипт для VLESS Shop Bot
# Автор: Gemini AI (адаптировано под проект evansvl)
# Версия: 1.0.0
# ==============================================================================

# Цвета для вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# --- ФУНКЦИЯ ПРОВЕРКИ ОШИБОК ---
handle_error() {
    echo -e "\n${RED}Ошибка на строке $1. Установка прервана.${NC}"
    exit 1
}

trap 'handle_error $LINENO' ERR

# --- НАЧАЛО УСТАНОВКИ ---
echo -e "${GREEN}--- Запуск установки VLESS Shop Bot ---${NC}"

# --- ШАГ 1: Проверка и установка системных зависимостей ---
echo -e "\n${CYAN}Шаг 1: Проверка системных зависимостей...${NC}"

# Функция для установки пакета, если он отсутствует
install_package() {
    if ! command -v $1 &> /dev/null; then
        echo -e "${YELLOW}Утилита '$1' не найдена. Устанавливаем...${NC}"
        sudo apt-get update
        sudo apt-get install -y $2
    else
        echo -e "${GREEN}✔ $1 уже установлен.${NC}"
    fi
}

install_package "git" "git"
install_package "docker" "docker.io"
install_package "docker-compose" "docker-compose"
install_package "nginx" "nginx"
install_package "curl" "curl"

if ! sudo systemctl is-active --quiet docker; then
    echo -e "${YELLOW}Сервис Docker не запущен. Запускаем...${NC}"
    sudo systemctl start docker
    sudo systemctl enable docker
fi

echo -e "${GREEN}✔ Все системные зависимости установлены.${NC}"

REPO_URL="https://github.com/evansvl/vless-shopbot.git"
PROJECT_DIR="vless-shopbot"

echo -e "\n${CYAN}Шаг 2: Клонирование репозитория...${NC}"
if [ -d "$PROJECT_DIR" ]; then
    echo -e "${YELLOW}Папка '$PROJECT_DIR' уже существует. Пропускаем клонирование.${NC}"
else
    git clone $REPO_URL
fi
cd $PROJECT_DIR

echo -e "${GREEN}✔ Репозиторий готов.${NC}"

echo -e "\n${CYAN}Шаг 3: Настройка Nginx для вебхуков YooKassa...${NC}"

read -p "Введите ваш домен (например, my-vpn-shop.com): " DOMAIN
read -p "Какой порт вы будете использовать для вебхуков YooKassa? (443 или 8443): " YOOKASSA_PORT
read -p "Укажите порт, на котором работает бот (по умолчанию 1488): " BOT_PORT
BOT_PORT=${BOT_PORT:-1488}

if [ "$YOOKASSA_PORT" != "443" ] && [ "$YOOKASSA_PORT" != "8443" ]; then
    echo -e "${RED}Ошибка: YooKassa поддерживает только порты 443 и 8443. Установка прервана.${NC}"
    exit 1
fi

NGINX_CONF_FILE="/etc/nginx/sites-available/$PROJECT_DIR.conf"
NGINX_ENABLED_FILE="/etc/nginx/sites-enabled/$PROJECT_DIR.conf"

if [ -f "$NGINX_CONF_FILE" ]; then
    echo -e "${YELLOW}Конфигурационный файл Nginx уже существует. Пропускаем.${NC}"
else
    echo -e "Создаем конфигурацию Nginx..."
    sudo bash -c "cat > $NGINX_CONF_FILE" <<EOF
server {
    listen ${YOOKASSA_PORT} ssl http2;
    listen [::]:${YOOKASSA_PORT} ssl http2;

    server_name ${DOMAIN};

    # Убедитесь, что у вас есть SSL сертификаты.
    # Этот скрипт предполагает, что вы используете Let's Encrypt (Certbot).
    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305';

    location /yookassa-webhook {
        proxy_pass http://127.0.0.1:${BOT_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # Перенаправляем корневой запрос на страницу логина
    location / {
        proxy_pass http://127.0.0.1:${BOT_PORT}/login;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
    sudo ln -s $NGINX_CONF_FILE $NGINX_ENABLED_FILE

    echo -e "${GREEN}✔ Конфигурация Nginx создана и активирована.${NC}"
    echo -e "${YELLOW}Проверяем синтаксис Nginx...${NC}"
    sudo nginx -t
    echo -e "${YELLOW}Перезагружаем Nginx...${NC}"
    sudo systemctl reload nginx
fi

echo -e "\n${CYAN}Шаг 4: Сборка и запуск Docker-контейнера...${NC}"
sudo docker-compose up -d --build

IP_ADDRESS=$(curl -s ifconfig.me || hostname -I | awk '{print $1}')

echo -e "\n\n${GREEN}=====================================================${NC}"
echo -e "${GREEN}      🎉 Установка и запуск успешно завершены! 🎉      ${NC}"
echo -e "${GREEN}=====================================================${NC}"
echo -e "\nВеб-панель доступна по одному из этих адресов:"
echo -e "  - Через ваш домен (рекомендуется): ${YELLOW}https://${DOMAIN}:${YOOKASSA_PORT}/login${NC}"
echo -e "  - Напрямую по IP (может не работать, если настроен файрвол): ${YELLOW}http://${IP_ADDRESS}:${BOT_PORT}/login${NC}"
echo -e "\nДанные для первого входа:"
echo -e "  - Логин:   ${CYAN}admin${NC}"
echo -e "  - Пароль:  ${CYAN}admin${NC}"
echo -e "\n${RED}ВАЖНО: Обязательно смените логин и пароль в панели управления!${NC}"
echo -e "\n${CYAN}Бот запущен в фоновом режиме. Для управления используйте команды:${NC}"
echo -e "  - Посмотреть логи: ${YELLOW}docker-compose logs -f${NC}"
echo -e "  - Остановить: ${YELLOW}docker-compose down${NC}"
echo -e "  - Запустить снова: ${YELLOW}docker-compose up -d${NC}"
echo -e "\n${CYAN}Не забудьте указать URL для вебхуков в личном кабинете YooKassa:${NC}"
echo -e "  - ${YELLOW}https://${DOMAIN}:${YOOKASSA_PORT}/yookassa-webhook${NC}"
echo -e "\n"```