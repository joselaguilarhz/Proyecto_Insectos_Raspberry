# routes/upload_routes.py
from flask import Blueprint, request, jsonify
from core.config import Config
from core.database import db
from core.roboflow_client import procesar_con_roboflow, extraer_prediccion
from models.models import Deteccion
import os
import shutil
from datetime import datetime
from werkzeug.utils import secure_filename

upload_bp = Blueprint("upload_bp", __name__)

def _asegurar_carpetas():
    for d in (Config.CAPTURE_DIR, Config.DETECTADAS_DIR, Config.NODETECCION_DIR):
        os.makedirs(d, exist_ok=True)

@upload_bp.route("/upload", methods=["POST"])
def upload_image():
    _asegurar_carpetas()

    file = request.files.get("file")
    camera_name = request.form.get("camera_name", Config.CAMERA_NAME)
    temp = request.form.get("temperature")
    hum = request.form.get("humidity")

    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    # Nombre de archivo con timestamp para evitar colisiones
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    fname = secure_filename(file.filename) or f"{camera_name}_{ts}.jpg"
    capture_path = os.path.join(Config.CAPTURE_DIR, f"{ts}_{fname}")

    file.save(capture_path)

    # Detectar con Roboflow
    result = procesar_con_roboflow(capture_path)
    insect, confidence = extraer_prediccion(result)

    # Mover según detección
    if insect:
        dest_dir = Config.DETECTADAS_DIR
    else:
        dest_dir = Config.NODETECCION_DIR

    final_path = os.path.join(dest_dir, os.path.basename(capture_path))
    try:
        shutil.copy2(capture_path, final_path)
    except Exception:
        final_path = capture_path  # fallback

    # Guardar en BD
    det = Deteccion(
        camera_name=camera_name,
        filename=os.path.basename(final_path),
        insect=insect,
        confidence=confidence,
        temperature=float(temp) if temp not in (None, "", "None") else None,
        humidity=float(hum) if hum not in (None, "", "None") else None,
    )
    db.session.add(det)
    db.session.commit()

    return jsonify({
        "status": "ok",
        "insect": insect,
        "confidence": confidence,
        "stored_in": "detectadas" if insect else "nodeteccion",
        "filename": os.path.basename(final_path)
    }), 200
