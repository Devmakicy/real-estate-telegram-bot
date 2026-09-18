import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("RAILWAY_VOLUME_MOUNT_PATH", BASE_DIR / "data"))
UPLOADS_DIR = DATA_DIR / "uploads"

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
]

# Группа с включёнными топиками (Forum). Бот должен быть админом с правом «Управление топиками».
_admin_group = os.getenv("ADMIN_GROUP_ID", "").strip()
ADMIN_GROUP_ID = int(_admin_group) if _admin_group.lstrip("-").isdigit() else 0

BOT_DISPLAY_NAME = os.getenv("BOT_DISPLAY_NAME", "Видеоролики недвижимость")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DATA_DIR / 'bot.db'}")
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("PORT", os.getenv("WEB_PORT", "8080")))

WELCOME_TEXT = """📋 Чтобы начать, отправьте мне прямо в этот чат:

• Либо ссылку на ваше объявление (с любого сайта недвижимости)
• Либо фотографии объекта (если ссылки под рукой нет)

Я сразу приступлю к работе и сделаю для вас крутой ролик по этим материалам!

Цена: 15000р

Жду ссылку или фото. Отправляйте прямо сюда 👇"""

BOT_DESCRIPTION = (
    "🎬 Профессиональные продающие ролики для объектов недвижимости. "
    "Отправьте ссылку на объявление или фото — получите готовый ролик. Цена: 15000₽"
)
