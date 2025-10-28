# core/config.py
import os
from dotenv import load_dotenv

load_dotenv()

def _sqlite_uri_from_path(path: str) -> str:
    # SQLAlchemy requiere 3 o 4 slashes según sea ruta absoluta
    path = os.path.abspath(path)
    return f"sqlite:///{path}"

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "smartfenix-key")
    # BD
    DB_PATH = os.getenv("DB_PATH", os.path.join(os.getcwd(), "app.db"))
    SQLALCHEMY_DATABASE_URI = _sqlite_uri_from_path(DB_PATH)
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Carpetas
    CAPTURE_DIR = os.getenv("CAPTURE_DIR", "uploads")
    DETECTADAS_DIR = os.getenv("DETECTADAS_DIR", "uploads_detectadas")
    NODETECCION_DIR = os.getenv("NODETECCION_DIR", "uploads_nodeteccion")

    # Roboflow (usaremos workflow)
    ROBOFLOW_API_KEY = os.getenv("ROBOFLOW_API_KEY")
    ROBOFLOW_WORKSPACE = os.getenv("ROBOFLOW_WORKSPACE")
    ROBOFLOW_WORKFLOW = os.getenv("ROBOFLOW_WORKFLOW")

    # Semilla de usuario/cámara
    DEFAULT_USERNAME = os.getenv("DEFAULT_USERNAME", "admin")
    DEFAULT_PASSWORD = os.getenv("DEFAULT_PASSWORD", "123")
    CAMERA_NAME = os.getenv("CAMERA_NAME", "camara-finca")
