#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sistema de Detección Automática de Insectos
===========================================

Este script captura imágenes usando la cámara de Raspberry Pi 5,
procesa las imágenes con Roboflow para detectar insectos,
envía notificaciones por Telegram y almacena los resultados en SQLite.

Autor: SmartFenix
Versión: 2.0
Fecha: 2025
"""

import os
import base64
import uuid
import logging
import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import requests
from inference_sdk import InferenceHTTPClient
from picamera2 import Picamera2
from dotenv import load_dotenv

# =============================================================================
# CONFIGURACIÓN DE LOGGING
# =============================================================================

logging.basicConfig(
    level=logging.INFO, 
    format='[%(asctime)s] %(levelname)s %(message)s'
)
logger = logging.getLogger()

# =============================================================================
# CARGA DE VARIABLES DE ENTORNO
# =============================================================================

def cargar_configuracion():
    """
    Carga la configuración desde archivo .env con manejo robusto de errores.
    
    Returns:
        bool: True si se cargó correctamente, False en caso contrario
    """
    # Definir ruta del archivo .env
    ENV_FILE = os.getenv("ENV_FILE", "/home/smartfenix/Proyecto_Insectos/.env")
    
    # Verificar existencia del archivo
    if not os.path.exists(ENV_FILE):
        logger.error(f"[ENV] El archivo .env no existe en: {ENV_FILE}")
        
        # Intentar rutas alternativas
        rutas_alternativas = [
            os.path.expanduser("~/.env"),
            os.path.join(os.getcwd(), ".env"),
            "/home/smartfenix/.env"
        ]
        
        for ruta_alt in rutas_alternativas:
            if os.path.exists(ruta_alt):
                ENV_FILE = ruta_alt
                logger.info(f"[ENV] Encontrado .env alternativo en: {ENV_FILE}")
                break
        else:
            logger.error("[ENV] No se encontró ningún archivo .env")
            return False
    
    # Cargar archivo .env
    cargado = load_dotenv(ENV_FILE, override=True)
    logger.info(f"[ENV] Archivo cargado: {cargado} desde {ENV_FILE}")
    
    # Verificar carga exitosa
    if not cargado:
        try:
            with open(ENV_FILE, 'r') as f:
                contenido = f.read()
                logger.info(f"[ENV] Contenido del archivo: {contenido[:200]}...")
        except PermissionError:
            logger.error(f"[ENV] Sin permisos para leer {ENV_FILE}")
        except Exception as e:
            logger.error(f"[ENV] Error leyendo {ENV_FILE}: {e}")
        return False
    
    # Verificar variables críticas
    variables_criticas = ["ROBOFLOW_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
    for nombre in variables_criticas:
        valor = os.getenv(nombre)
        if valor:
            # Enmascarar claves por seguridad
            valor_enmascarado = f"{valor[:8]}..." if len(valor) > 8 else "SET"
            logger.info(f"[ENV] {nombre}={valor_enmascarado}")
        else:
            logger.warning(f"[ENV] {nombre}=FALTANTE")
    
    return True

# Cargar configuración al inicio
configuracion_ok = cargar_configuracion()

# =============================================================================
# VARIABLES DE CONFIGURACIÓN
# =============================================================================

# Configuración general
CAMERA_NAME      = os.getenv("CAMERA_NAME", "camara-finca")
CAPTURE_DIR      = Path(os.getenv("CAPTURE_DIR", "/home/smartfenix/fotos_cam/entrantes"))
DETECTADAS_DIR   = Path(os.getenv("DETECTADAS_DIR", "/home/smartfenix/fotos_cam/detectadas"))
NODETECCION_DIR  = Path(os.getenv("NODETECCION_DIR", "/home/smartfenix/fotos_cam/nodeteccion"))
DB_PATH          = os.getenv("DB_PATH", "/home/smartfenix/Proyecto_Insectos/app.db")
INTERVAL         = int(os.getenv("INTERVAL", "30"))

# Configuración de cámara
WIDTH            = int(os.getenv("WIDTH", "2028"))
HEIGHT           = int(os.getenv("HEIGHT", "1520"))
AWBGAINS         = os.getenv("AWBGAINS", "1.8,1.2").strip()
AWB              = os.getenv("AWB", "daylight")

# Configuración de Roboflow
API_KEY          = os.getenv("ROBOFLOW_API_KEY", "").strip()
WORKSPACE_NAME   = os.getenv("ROBOFLOW_WORKSPACE", "detectorinsectos")
WORKFLOW_ID      = os.getenv("ROBOFLOW_WORKFLOW", "detect-count-and-visualize-7")

# Configuración de Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Mostrar configuración cargada
logger.info(f"[CONFIG] CAMERA_NAME={CAMERA_NAME}")
logger.info(f"[CONFIG] CAPTURE_DIR={CAPTURE_DIR}")
logger.info(f"[CONFIG] DETECTADAS_DIR={DETECTADAS_DIR}")
logger.info(f"[CONFIG] NODETECCION_DIR={NODETECCION_DIR}")
logger.info(f"[CONFIG] DB_PATH={DB_PATH}")
logger.info(f"[CONFIG] INTERVAL={INTERVAL} segundos")
logger.info(f"[CONFIG] RESOLUCIÓN={WIDTH}x{HEIGHT}")
logger.info(f"[CONFIG] AWB={AWB}, AWBGAINS={AWBGAINS}")

# =============================================================================
# INICIALIZACIÓN DE DIRECTORIOS
# =============================================================================

def crear_directorios():
    """Crea todos los directorios necesarios para el funcionamiento del sistema."""
    directorios = [CAPTURE_DIR, DETECTADAS_DIR, NODETECCION_DIR, Path(DB_PATH).parent]
    
    for directorio in directorios:
        try:
            directorio.mkdir(parents=True, exist_ok=True)
            logger.info(f"[DIR] Directorio asegurado: {directorio}")
        except Exception as e:
            logger.error(f"[DIR] Error creando directorio {directorio}: {e}")
            raise

crear_directorios()

# =============================================================================
# GESTIÓN DE BASE DE DATOS
# =============================================================================

def inicializar_base_datos():
    """
    Inicializa la base de datos SQLite creando las tablas necesarias.
    
    Tablas:
    - users: Almacena información de usuarios/cámaras
    - detecciones: Almacena historial de detecciones
    """
    try:
        # Asegurar que existe el directorio de la BD
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        
        with sqlite3.connect(DB_PATH) as conexion:
            # Configurar SQLite para mejor rendimiento
            conexion.execute("PRAGMA journal_mode=WAL;")
            conexion.execute("PRAGMA foreign_keys=ON;")
            
            # Crear tabla de usuarios
            conexion.execute("""
                CREATE TABLE IF NOT EXISTS users (
                  id INTEGER PRIMARY KEY,
                  username TEXT NOT NULL,
                  camera_name TEXT NOT NULL UNIQUE,
                  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Crear tabla de detecciones
            conexion.execute("""
                CREATE TABLE IF NOT EXISTS detecciones (
                  id INTEGER PRIMARY KEY,
                  user_id INTEGER NOT NULL,
                  nombre_archivo TEXT,
                  insecto_detectado TEXT,
                  fecha DATETIME,
                  ruta_imagen TEXT,
                  enviado_telegram BOOLEAN DEFAULT 0,
                  FOREIGN KEY(user_id) REFERENCES users(id)
                )
            """)
            
            # Crear índice para consultas rápidas por fecha
            conexion.execute("""
                CREATE INDEX IF NOT EXISTS ix_detecciones_fecha 
                ON detecciones (fecha)
            """)
        
        logger.info(f"[DB] Base de datos inicializada en: {DB_PATH}")
        
    except Exception as e:
        logger.error(f"[DB] Error inicializando base de datos: {e}")
        raise

def asegurar_usuario():
    """
    Garantiza que existe un usuario en la base de datos para esta cámara.
    
    Returns:
        int: ID del usuario en la base de datos
    """
    nombre_usuario = os.getenv("DEFAULT_USERNAME", "smart")
    
    try:
        with sqlite3.connect(DB_PATH) as conexion:
            conexion.execute("PRAGMA foreign_keys=ON;")
            
            # Insertar usuario si no existe (INSERT OR IGNORE)
            conexion.execute(
                "INSERT OR IGNORE INTO users (username, camera_name) VALUES (?, ?)",
                (nombre_usuario, CAMERA_NAME)
            )
            
            # Obtener ID del usuario
            fila = conexion.execute(
                "SELECT id FROM users WHERE camera_name = ?",
                (CAMERA_NAME,)
            ).fetchone()
            
            if not fila:
                raise RuntimeError(f"No se pudo obtener user_id para la cámara {CAMERA_NAME}")
            
            user_id = fila[0]
            logger.info(f"[DB] Usuario asegurado: {nombre_usuario} (ID: {user_id})")
            return user_id
            
    except Exception as e:
        logger.error(f"[DB] Error asegurando usuario: {e}")
        raise

def insertar_deteccion(user_id, nombre_archivo, insecto, ruta_imagen, enviado_telegram=False):
    """
    Inserta una nueva detección en la base de datos.
    
    Args:
        user_id (int): ID del usuario
        nombre_archivo (str): Nombre del archivo de imagen
        insecto (str): Tipo de insecto detectado o "No detectado"
        ruta_imagen (str): Ruta completa al archivo de imagen
        enviado_telegram (bool): Si se envió notificación por Telegram
    """
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        with sqlite3.connect(DB_PATH) as conexion:
            conexion.execute("PRAGMA foreign_keys=ON;")
            conexion.execute("""
                INSERT INTO detecciones
                    (user_id, nombre_archivo, insecto_detectado, fecha, ruta_imagen, enviado_telegram)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, nombre_archivo, insecto, fecha, ruta_imagen, int(bool(enviado_telegram))))
        
        logger.info(f"[DB] Detección registrada: {insecto}")
        
    except Exception as e:
        logger.error(f"[DB] Error insertando detección: {e}")
        raise

# =============================================================================
# CLIENTE ROBOFLOW PARA DETECCIÓN DE INSECTOS
# =============================================================================

def inicializar_cliente_roboflow():
    """
    Inicializa el cliente de Roboflow para procesamiento de imágenes.
    
    Returns:
        InferenceHTTPClient o None: Cliente inicializado o None si hay error
    """
    if not API_KEY:
        logger.warning("[ROBOFLOW] API_KEY no definido; el procesado fallará.")
        return None
    
    try:
        cliente = InferenceHTTPClient(
            api_url="https://detect.roboflow.com", 
            api_key=API_KEY
        )
        logger.info("[ROBOFLOW] Cliente inicializado correctamente")
        return cliente
    except Exception as e:
        logger.error(f"[ROBOFLOW] Error inicializando cliente: {e}")
        return None

# Inicializar cliente global
rf_client = inicializar_cliente_roboflow()

def procesar_con_roboflow(ruta_imagen):
    """
    Procesa una imagen usando el workflow de Roboflow para detectar insectos.
    
    Args:
        ruta_imagen (str): Ruta al archivo de imagen a procesar
        
    Returns:
        tuple: (predicciones, imagen_anotada_b64)
            - predicciones: Lista de objetos detectados
            - imagen_anotada_b64: Imagen con anotaciones en base64 (si disponible)
    """
    if not rf_client:
        logger.warning("[ROBOFLOW] Cliente no disponible")
        return [], None
    
    try:
        # Ejecutar workflow de detección
        resultado = rf_client.run_workflow(
            workspace_name=WORKSPACE_NAME,
            workflow_id=WORKFLOW_ID,
            images={"image": ruta_imagen},
            use_cache=True
        )
        logger.info("[ROBOFLOW] Procesamiento completado")
        
    except Exception as e:
        logger.error(f"[ROBOFLOW] Error en procesamiento: {e}")
        return [], None
    
    # Extraer predicciones y imagen anotada del resultado
    predicciones = []
    imagen_anotada_b64 = None
    
    # El resultado puede ser una lista o un diccionario
    bloques = resultado if isinstance(resultado, list) else [resultado]
    
    for bloque in bloques:
        if not isinstance(bloque, dict):
            continue
            
        # Buscar predicciones en diferentes formatos de respuesta
        inner = bloque.get('predictions') or bloque
        
        if isinstance(inner, dict) and 'predictions' in inner:
            predicciones = inner.get('predictions', [])
            imagen_anotada_b64 = inner.get('output_image')
            break
        elif isinstance(inner, list):
            predicciones = inner
            break
    
    logger.info(f"[ROBOFLOW] Predicciones encontradas: {len(predicciones)}")
    return predicciones, imagen_anotada_b64

# =============================================================================
# NOTIFICACIONES POR TELEGRAM
# =============================================================================

def enviar_telegram(foto_b64, mensaje):
    """
    Envía una foto con mensaje por Telegram.
    
    Args:
        foto_b64 (str): Imagen codificada en base64
        mensaje (str): Texto del mensaje a enviar
        
    Returns:
        bool: True si se envió correctamente, False en caso contrario
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("[TELEGRAM] Token o Chat ID no definidos; no se enviará.")
        return False
    
    try:
        # Construir URL de la API de Telegram
        url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto'
        
        # Decodificar imagen base64
        bytes_imagen = base64.b64decode(foto_b64)
        
        # Preparar datos para envío
        archivos = {'photo': ('deteccion.jpg', bytes_imagen)}
        datos = {
            'chat_id': TELEGRAM_CHAT_ID, 
            'caption': mensaje, 
            'parse_mode': 'Markdown'
        }
        
        # Enviar petición HTTP
        respuesta = requests.post(url, files=archivos, data=datos, timeout=20)
        
        if respuesta.status_code == 200:
            logger.info("[TELEGRAM] Mensaje enviado correctamente")
            return True
        else:
            logger.warning(f"[TELEGRAM] Error {respuesta.status_code}: {respuesta.text[:200]}")
            return False
            
    except Exception as e:
        logger.error(f"[TELEGRAM] Error enviando: {e}")
        return False

# =============================================================================
# GESTIÓN DE CÁMARA
# =============================================================================

def inicializar_camara():
    """
    Inicializa y configura la c�mara Raspberry Pi con la misma configuraci�n
    vista en rpicam-still. Por defecto AWB en AUTO para evitar tinte verde.
    Si quieres forzar ganancias manuales, pon FORCE_AWBGAINS=true en el .env.
    """
    try:
        camara = Picamera2()

        # Streams como muestra rpicam-still: main YUV420 + raw SBGGR12
        configuracion = camara.create_still_configuration(
            main={"size": (WIDTH, HEIGHT), "format": "YUV420"},
            raw={"size": (WIDTH, HEIGHT), "format": "SBGGR12"}
        )
        camara.configure(configuracion)

        controles = {}

        # --- Modo por defecto: AWB AUTO (recomendado para evitar dominantes) ---
        controles["AwbMode"] = 0  # 0=auto, 1=incandescent, 2=fluorescent, 3=daylight, 4=cloudy

        # --- Opcional: forzar ganancias manuales (puede causar dominante si no son perfectas) ---
        force_gains = os.getenv("FORCE_AWBGAINS", "false").strip().lower() in ("1", "true", "yes", "y", "on")
        if force_gains and AWBGAINS:
            try:
                r, b = [float(x) for x in AWBGAINS.split(",")]
                # Para usar gains manuales, desactiva el AWB y aplica gains:
                controles["AwbEnable"] = False
                controles["ColourGains"] = (r, b)
                logger.info(f"[CAMERA] Usando ColourGains manuales R={r}, B={b}")
                # Si adem�s quieres forzar un preset concreto:
                modos_awb = {"auto": 0, "incandescent": 1, "fluorescent": 2, "daylight": 3, "cloudy": 4}
                controles["AwbMode"] = modos_awb.get(AWB, 3)
            except Exception:
                logger.warning("[CAMERA] AWBGAINS inv�lido; sigo en AWB AUTO.")
                controles["AwbEnable"] = True
                controles["AwbMode"] = 0

        camara.set_controls(controles)
        logger.info("[CAMERA] C�mara inicializada (main=YUV420, raw=SBGGR12, AWB AUTO por defecto)")
        return camara

    except Exception as e:
        logger.error(f"[CAMERA] Error inicializando c�mara: {e}")
        raise
    """
    Inicializa y configura la c�mara Raspberry Pi con la misma configuraci�n
    usada en rpicam-still (2028x1520 RAW SBGGR12 + YUV420, AWB daylight/gains).
    
    Returns:
        Picamera2: Objeto de c�mara configurado
    """
    try:
        camara = Picamera2()

        # Configuraci�n de streams como en rpicam-still
        configuracion = camara.create_still_configuration(
            main={"size": (WIDTH, HEIGHT), "format": "YUV420"},
            raw={"size": (WIDTH, HEIGHT), "format": "SBGGR12"}
        )
        camara.configure(configuracion)

        # === Controles de balance de blancos ===
        controles = {}

        # Si hay AWBGAINS definidos -> aplicar manualmente
        if AWBGAINS:
            try:
                r, b = [float(x) for x in AWBGAINS.split(",")]
                controles["ColourGains"] = (r, b)
                logger.info(f"[CAMERA] ColourGains configurado: R={r}, B={b}")
            except Exception:
                logger.warning("[CAMERA] AWBGAINS inv�lido; usando AWB preset.")

        # Si no hay AWBGAINS v�lidos -> usar modo AWB (daylight por defecto)
        if not AWBGAINS or "ColourGains" not in controles:
            modos_awb = {
                "auto": 0,
                "incandescent": 1,
                "fluorescent": 2,
                "daylight": 3,
                "cloudy": 4
            }
            controles["AwbMode"] = modos_awb.get(AWB, 3)
            logger.info(f"[CAMERA] AWB Mode configurado: {AWB}")

        # Aplicar controles
        if controles:
            camara.set_controls(controles)

        logger.info("[CAMERA] C�mara inicializada correctamente con config rpicam-still")
        return camara

    except Exception as e:
        logger.error(f"[CAMERA] Error inicializando c�mara: {e}")
        raise
# =============================================================================
# FUNCIÓN PRINCIPAL
# =============================================================================

def main():
    """
    Función principal que ejecuta el bucle de detección automática.
    
    Flujo de trabajo:
    1. Inicializar componentes (BD, usuario, cámara)
    2. Bucle infinito:
       - Capturar imagen
       - Procesar con Roboflow
       - Enviar notificación por Telegram
       - Mover imagen a carpeta correspondiente
       - Registrar en base de datos
       - Esperar intervalo configurado
    """
    logger.info("🚀 Iniciando Sistema de Detección de Insectos")
    
    # Verificar configuración crítica
    if not configuracion_ok:
        logger.error("[MAIN] Error en configuración, abortando")
        return
    
    if not API_KEY:
        logger.error("[MAIN] ROBOFLOW_API_KEY es obligatorio")
        return
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("[MAIN] Telegram no configurado, no habrá notificaciones")
    
    try:
        # Inicializar componentes del sistema
        logger.info("[MAIN] Inicializando componentes...")
        inicializar_base_datos()
        user_id = asegurar_usuario()
        camara = inicializar_camara()
        
        # Iniciar cámara
        camara.start()
        time.sleep(0.4)  # Tiempo para estabilización
        
        logger.info("[MAIN] 🎯 Sistema iniciado - Comenzando capturas automáticas")
        
        # Bucle principal de detección
        while True:
            # Generar nombre único para la imagen
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            id_unico = uuid.uuid4().hex[:8]
            nombre_archivo = f"{CAMERA_NAME}_{id_unico}_{timestamp}.jpg"
            ruta_imagen = CAPTURE_DIR / nombre_archivo
            
            # === CAPTURA DE IMAGEN ===
            try:
                camara.capture_file(str(ruta_imagen))
                logger.info(f"📸 Imagen capturada: {nombre_archivo}")
            except Exception as e:
                logger.error(f"[CAMERA] Error en captura: {e}")
                continue
            
            # === PROCESAMIENTO CON ROBOFLOW ===
            predicciones, imagen_anotada_b64 = procesar_con_roboflow(str(ruta_imagen))
            
            # Determinar resultado y carpeta destino
            if predicciones:
                insecto_detectado = predicciones[0].get('class', 'desconocido')
                confianza = predicciones[0].get('confidence', 0)
                carpeta_destino = DETECTADAS_DIR
                logger.info(f"🐛 ¡Insecto detectado! Tipo: {insecto_detectado} (confianza: {confianza:.2f})")
            else:
                insecto_detectado = "ninguno"
                carpeta_destino = NODETECCION_DIR
                logger.info("🚫 No se detectaron insectos")
            
            ruta_final = carpeta_destino / nombre_archivo
            
            # === NOTIFICACIÓN POR TELEGRAM ===
            telegram_enviado = False
            if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
                try:
                    # Usar imagen anotada si está disponible, sino la original
                    if imagen_anotada_b64:
                        foto_para_enviar = imagen_anotada_b64
                    else:
                        with open(ruta_imagen, 'rb') as f:
                            foto_para_enviar = base64.b64encode(f.read()).decode()
                    
                    mensaje = f"🐛 Detección: *{insecto_detectado}*\n📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                    telegram_enviado = enviar_telegram(foto_para_enviar, mensaje)
                    
                except Exception as e:
                    logger.error(f"[TELEGRAM] Error preparando envío: {e}")
            
            # === MOVER IMAGEN A CARPETA FINAL ===
            try:
                shutil.move(str(ruta_imagen), str(ruta_final))
                logger.info(f"🗂️ Imagen archivada en: {carpeta_destino.name}")
            except Exception as e:
                logger.error(f"[FILE] Error moviendo imagen: {e}")
                # Usar la ruta original si no se pudo mover
                ruta_final = ruta_imagen
            
            # === REGISTRO EN BASE DE DATOS ===
            try:
                insertar_deteccion(
                    user_id, 
                    nombre_archivo, 
                    insecto_detectado, 
                    str(ruta_final), 
                    telegram_enviado
                )
                logger.info("💾 Detección registrada en base de datos")
            except Exception as e:
                logger.error(f"[DB] Error registrando detección: {e}")
            
            # === ESPERA ANTES DE SIGUIENTE CAPTURA ===
            logger.info(f"⏱️ Esperando {INTERVAL} segundos para próxima captura...")
            time.sleep(INTERVAL)
    
    except KeyboardInterrupt:
        logger.info("🛑 Sistema detenido por el usuario")
    
    except Exception as e:
        logger.error(f"[MAIN] Error crítico: {e}")
        raise
    
    finally:
        # Limpiar recursos
        try:
            camara.stop()
            logger.info("[CAMERA] Cámara detenida correctamente")
        except Exception:
            pass

# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================

if __name__ == "__main__":
    main()