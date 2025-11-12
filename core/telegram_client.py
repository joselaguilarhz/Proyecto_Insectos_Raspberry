import os
import requests
from core.config import Config

# =====================================================
# ⚙️ Configuración desde .env
# =====================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", getattr(Config, "TELEGRAM_BOT_TOKEN", None))
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", getattr(Config, "TELEGRAM_CHAT_ID", None))

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else None


# =====================================================
# 🤖 Función principal: enviar mensaje + foto
# =====================================================
def enviar_mensaje_telegram(mensaje: str, image_path: str = None):
    """Envía un mensaje y opcionalmente una imagen al chat configurado en Telegram."""

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ No se ha configurado TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en el entorno.")
        return False

    try:
        # --- Enviar mensaje ---
        print(f"📤 Enviando mensaje a Telegram: {mensaje}")
        resp_msg = requests.post(
            f"{BASE_URL}/sendMessage",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": mensaje
            },
            timeout=15
        )
        print(f"✅ Respuesta Telegram mensaje: {resp_msg.status_code}")

        # --- Enviar imagen (si existe) ---
        if image_path and os.path.exists(image_path):
            print(f"🖼️ Enviando imagen: {image_path}")
            with open(image_path, "rb") as img:
                resp_img = requests.post(
                    f"{BASE_URL}/sendPhoto",
                    data={"chat_id": TELEGRAM_CHAT_ID, "caption": mensaje},
                    files={"photo": img},
                    timeout=20
                )
            print(f"✅ Respuesta Telegram imagen: {resp_img.status_code}")
        elif image_path:
            print(f"⚠️ Imagen no encontrada en la ruta: {image_path}")

        return True

    except Exception as e:
        print(f"❌ Error enviando mensaje o imagen a Telegram: {e}")
        return False

