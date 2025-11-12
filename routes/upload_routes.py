import os
import shutil
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from core.config import Config
from core.database import db
from models.models import Deteccion
from core.roboflow_client import procesar_imagen_roboflow

upload_bp = Blueprint("upload_bp", __name__)

# =====================================================
# 🔧 Asegurar que las carpetas existen
# =====================================================
def _asegurar_carpetas():
    for carpeta in [
        Config.CAPTURE_DIR,
        Config.DETECTADAS_DIR,
        Config.NODETECCION_DIR,
    ]:
        os.makedirs(carpeta, exist_ok=True)

# =====================================================
# 📤 Endpoint principal de subida. En las Raspberrys se debe tener en cuenta este endpoint que es el que se encarga 
# =====================================================
@upload_bp.route("/upload", methods=["POST"])
def upload_image():
    print("\n===============================")
    print("📸 POST /upload recibido")
    _asegurar_carpetas()

    # ---- Obtener datos del formulario ----
    file = request.files.get("file")
    camera_name = request.form.get("camera_name", Config.CAMERA_NAME)
    temperature = request.form.get("temperature")
    humidity = request.form.get("humidity")

    if not file:
        print("❌ No se recibió archivo")
        return jsonify({"error": "No file uploaded"}), 400

    # ---- Guardar imagen original ----
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    fname = secure_filename(file.filename) or f"{camera_name}_{ts}.jpg"
    capture_path = os.path.join(Config.CAPTURE_DIR, f"{ts}_{fname}")
    print(f"💾 Guardando imagen: {capture_path}")
    file.save(capture_path)

    # =====================================================
    # 🧠 Procesamiento con Roboflow
    # =====================================================
    insect, confidence = None, None
    processed_filename = None
    
    try:
        print("🚀 Enviando a Roboflow...")
        base_name = os.path.splitext(os.path.basename(capture_path))[0]
        processed_path = os.path.join(Config.CAPTURE_DIR, f"{base_name}_processed.jpg")

        insect, confidence, result, imagen_guardada = procesar_imagen_roboflow(
            capture_path, processed_output_path=processed_path
        )
        print(f"🪲 Detección: {insect}, confianza={confidence}")

        if imagen_guardada:
            processed_filename = os.path.basename(processed_path)
            print(f"✅ Imagen procesada guardada: {processed_filename}")
    except Exception as e:
        print(f"⚠️ Error procesando en Roboflow: {e}")

    # =====================================================
    # 📦 Copiar imágenes a carpeta destino
    # =====================================================
    try:
        dest_dir = Config.DETECTADAS_DIR if insect else Config.NODETECCION_DIR

        # Copiar original
        final_path = os.path.join(dest_dir, os.path.basename(capture_path))
        shutil.copy2(capture_path, final_path)
        print(f"📁 Imagen original copiada a: {final_path}")

        # Copiar procesada si existe
        if processed_filename:
            processed_src = os.path.join(Config.CAPTURE_DIR, processed_filename)
            processed_dest = os.path.join(dest_dir, processed_filename)
            if os.path.exists(processed_src):
                shutil.copy2(processed_src, processed_dest)
                print(f"📁 Imagen procesada copiada a: {processed_dest}")

    except Exception as e:
        print(f"⚠️ Error moviendo imágenes: {e}")
        final_path = capture_path

    # =====================================================
    # 🗄️ Guardar detección en base de datos
    # =====================================================
    try:
        det = Deteccion(
            camera_name=camera_name,
            filename=os.path.basename(final_path),
            insect=insect,
            confidence=confidence,
            temperature=float(temperature) if temperature else None,
            humidity=float(humidity) if humidity else None,
            processed_filename=processed_filename,   # 👈 NUEVO CAMPO
        )
        db.session.add(det)
        db.session.commit()
        print("✅ Registro insertado en BD correctamente")
    except Exception as e:
        print(f"⚠️ Error guardando en BD: {e}")
        db.session.rollback()

    # =====================================================
    # 🤖 Enviar mensaje a Telegram
    # =====================================================
    try:
        from core.telegram_client import enviar_mensaje_telegram

        if insect:
            conf_txt = f"{confidence:.2f}%" if confidence is not None else "N/A"
            mensaje = f"📸 {camera_name}: 🪲 {insect} ({conf_txt})"
            imagen_a_enviar = os.path.join(dest_dir, processed_filename) if processed_filename else final_path
        else:
            mensaje = f"📸 {camera_name}: ❌ Sin detección de insectos"
            imagen_a_enviar = final_path

        enviar_mensaje_telegram(mensaje, imagen_a_enviar)
        print("📤 Mensaje enviado a Telegram correctamente")
    except Exception as e:
        print(f"⚠️ Error enviando a Telegram: {e}")

    # =====================================================
    # 🧾 Respuesta final
    # =====================================================
    print("✅ Proceso de subida completado")
    print("===============================\n")

    return jsonify({
        "status": "ok",
        "camera": camera_name,
        "insect": insect,
        "confidence": confidence,
        "filename": os.path.basename(final_path),
        "processed_filename": processed_filename
    }), 200

    