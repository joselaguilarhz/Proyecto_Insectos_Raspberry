import os
import json
import base64
from inference_sdk import InferenceHTTPClient
from core.config import Config


# =====================================================
# ⚙️ Configuración
# =====================================================
ROBOFLOW_API_KEY = os.getenv("ROBOFLOW_API_KEY", getattr(Config, "ROBOFLOW_API_KEY", None))
ROBOFLOW_WORKSPACE = os.getenv("ROBOFLOW_WORKSPACE", getattr(Config, "ROBOFLOW_WORKSPACE", None))
ROBOFLOW_WORKFLOW = os.getenv("ROBOFLOW_WORKFLOW", getattr(Config, "ROBOFLOW_WORKFLOW", None))

# Inicializar cliente Roboflow
rf_client = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key=ROBOFLOW_API_KEY
)


# =====================================================
# 🚀 Procesar imagen con Roboflow Workflow
# =====================================================
def procesar_con_roboflow(image_path):
    """
    Envía una imagen al workflow de Roboflow mediante el SDK oficial.
    Devuelve el JSON de respuesta completo o None si falla.
    """
    if not ROBOFLOW_API_KEY:
        print("❌ Falta ROBOFLOW_API_KEY en el entorno.")
        return None

    if not ROBOFLOW_WORKSPACE or not ROBOFLOW_WORKFLOW:
        print("❌ Faltan configuraciones de workspace o workflow.")
        return None

    if not os.path.exists(image_path):
        print(f"❌ Imagen no encontrada: {image_path}")
        return None

    try:
        print(f"🚀 Enviando imagen a Roboflow...")
        print(f"   🌐 Workspace: {ROBOFLOW_WORKSPACE}")
        print(f"   🔧 Workflow: {ROBOFLOW_WORKFLOW}")
        print(f"   📷 Imagen: {os.path.basename(image_path)}")

        result = rf_client.run_workflow(
            workspace_name=ROBOFLOW_WORKSPACE,
            workflow_id=ROBOFLOW_WORKFLOW,
            images={"image": image_path},
            use_cache=False
        )

        print("✅ Respuesta recibida de Roboflow:")
        print(json.dumps(result, indent=2))
        return result

    except Exception as e:
        print(f"❌ Error procesando imagen con Roboflow: {e}")
        import traceback
        traceback.print_exc()
        return None


# =====================================================
# 🧠 Extraer detección del JSON
# =====================================================
def extraer_prediccion(data):
    """
    Devuelve (insecto_detectado, confianza)
    compatible con el formato real devuelto por inference_sdk.
    """
    if not data:
        print("⚠️ No se recibió respuesta válida de Roboflow.")
        return None, None

    try:
        # El SDK devuelve una lista con 1 elemento
        if isinstance(data, list) and len(data) > 0:
            first = data[0]
            inner = first.get("predictions") if isinstance(first, dict) else None
            if inner and isinstance(inner, dict):
                preds = inner.get("predictions")
                if isinstance(preds, list) and len(preds) > 0:
                    det = preds[0]
                    insect = det.get("class", "Desconocido")
                    confidence = det.get("confidence", None)
                    if isinstance(confidence, (int, float)):
                        confidence = round(confidence * 100, 2)
                    print(f"🪲 Detección extraída correctamente: {insect} ({confidence}%)")
                    return insect, confidence

        # Si no coincide con el formato anterior
        print("⚠️ No se pudieron extraer detecciones del formato recibido.")
        return None, None

    except Exception as e:
        print(f"❌ Error analizando respuesta Roboflow: {e}")
        import traceback
        traceback.print_exc()
        return None, None


# =====================================================
# 🖼️ Extraer imagen procesada (con bounding box)
# =====================================================
def extraer_imagen_procesada(data, output_path):
    """
    Extrae la imagen procesada del workflow (output_image con bounding box)
    y la guarda en output_path.
    
    Retorna True si se guardó correctamente, False en caso contrario.
    """
    if not data:
        print("⚠️ No hay datos para extraer imagen procesada.")
        return False
    
    try:
        # El SDK devuelve una lista con 1 elemento
        if isinstance(data, list) and len(data) > 0:
            first = data[0]
            
            # Buscar el campo "output_image"
            output_image = first.get("output_image")
            
            if output_image:
                # La imagen viene en base64 con prefijo "data:image/jpeg;base64,"
                if isinstance(output_image, str):
                    # Remover el prefijo si existe
                    if "base64," in output_image:
                        output_image = output_image.split("base64,")[1]
                    
                    # Decodificar y guardar
                    image_data = base64.b64decode(output_image)
                    with open(output_path, 'wb') as f:
                        f.write(image_data)
                    
                    print(f"✅ Imagen procesada guardada en: {output_path}")
                    return True
                else:
                    print("⚠️ output_image no es una cadena base64 válida")
                    return False
            else:
                print("⚠️ No se encontró 'output_image' en la respuesta")
                return False
        
        print("⚠️ Formato de respuesta no reconocido para imagen procesada")
        return False
        
    except Exception as e:
        print(f"❌ Error extrayendo imagen procesada: {e}")
        import traceback
        traceback.print_exc()
        return False


# =====================================================
# 🧩 Función combinada
# =====================================================
def procesar_imagen_roboflow(image_path, processed_output_path=None):
    """
    Devuelve (insecto, confianza, data_cruda, imagen_procesada_guardada).
    
    Si processed_output_path es proporcionado, intenta guardar la imagen procesada.
    """
    data = procesar_con_roboflow(image_path)
    insect, confidence = extraer_prediccion(data)
    
    imagen_guardada = False
    if processed_output_path and data:
        imagen_guardada = extraer_imagen_procesada(data, processed_output_path)
    
    return insect, confidence, data, imagen_guardada