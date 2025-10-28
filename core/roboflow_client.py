# core/roboflow_client.py
import os
import requests

from core.config import Config

def procesar_con_roboflow(image_path: str) -> dict:
    """
    Envía la imagen al workflow de Roboflow y devuelve el JSON.
    Estructura esperada (simplificada):
    {
      "predictions": [
        { "class": "mosca_del_olivo", "confidence": 0.91, ... }
      ],
      ...
    }
    """
    api_key = Config.ROBOFLOW_API_KEY
    workspace = Config.ROBOFLOW_WORKSPACE
    workflow = Config.ROBOFLOW_WORKFLOW

    if not api_key or not workspace or not workflow:
        return {"error": "Faltan variables de Roboflow en .env"}

    url = f"https://detect.roboflow.com/{workspace}/{workflow}?api_key={api_key}"

    with open(image_path, "rb") as f:
        files = {"file": f}
        resp = requests.post(url, files=files, timeout=60)

    if not resp.ok:
        return {"error": f"Roboflow {resp.status_code}: {resp.text}"}

    return resp.json()


def extraer_prediccion(resultado: dict):
    """
    Devuelve (clase, confianza) o (None, None) si no hay predicciones.
    """
    if not resultado or "predictions" not in resultado:
        return None, None

    preds = resultado.get("predictions", [])
    if not preds:
        return None, None

    # Si el workflow devuelve múltiples, tomamos el más confiado
    best = max(preds, key=lambda p: p.get("confidence", 0))
    return best.get("class"), float(best.get("confidence", 0.0))
