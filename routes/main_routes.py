from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urljoin, urlparse
from datetime import datetime, timedelta

from flask import (
    Blueprint, abort, flash, redirect, render_template, jsonify,
    request, send_from_directory, url_for
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func

from core.config import Config
from core.database import db
from models.models import Deteccion, Usuario


main_bp = Blueprint("main_bp", __name__)

@main_bp.route('/')
def root_redirect():
    return redirect(url_for('main_bp.detecciones'))


_IMAGE_DIRS = [
    Path(Config.DETECTADAS_DIR),
    Path(Config.NODETECCION_DIR),
    Path(Config.CAPTURE_DIR),
]

_RECOMENDACIONES = {
    "mosca_del_olivo": {
        "nombre": "Mosca del olivo (Bactrocera oleae)",
        "descripcion": (
            "La mosca del olivo es una de las principales plagas que afectan a este cultivo. "
            "Aparece de primavera a otoño y causa pérdida de calidad del aceite. "
            "Más de 2 capturas semanales indican riesgo alto."
        ),
        "accion": (
            "Monitorear diariamente y revisar larvas en frutos. "
            "Si hay incremento, aplicar tratamiento autorizado y reforzar trampas."
        ),
    },
    "algodoncillo": {
        "nombre": "Algodoncillo (Planococcus citri)",
        "descripcion": (
            "Insecto chupador que afecta hojas y frutos, produce melaza y fomenta hongos. "
            "Se da en ambientes cálidos y secos, sobre todo a finales de verano."
        ),
        "accion": (
            "Realizar poda sanitaria, colocar trampas cromáticas y aplicar control biológico si persiste."
        ),
    },
}


def _locate_file(filename: str) -> Optional[Tuple[str, str]]:
    safe_name = Path(filename).name
    for directory in _IMAGE_DIRS:
        candidate = directory / safe_name
        if candidate.exists():
            return str(directory), safe_name
    return None


def _is_safe_next(target: Optional[str]) -> bool:
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc


# ==============================================
# ✅ VISTA PRINCIPAL (fusionada index + detecciones)
# ==============================================
@main_bp.route('/detecciones')
@login_required
def detecciones():
    """Vista de dashboard y detecciones fusionadas (versión estable)"""

    filtros = {
        'insecto': request.args.get('insecto', ''),
        'cam': request.args.get('cam', ''),
        'desde': request.args.get('desde', ''),
        'hasta': request.args.get('hasta', ''),
        'solo': request.args.get('solo', '')
    }

    page = request.args.get('page', 1, type=int)
    per_page = 20

    query = Deteccion.query

    # === Aplicar filtros ===
    if filtros['insecto']:
        query = query.filter(Deteccion.insect == filtros['insecto'])
    if filtros['cam']:
        query = query.filter(Deteccion.camera_name == filtros['cam'])
    if filtros['desde']:
        try:
            fecha_desde = datetime.strptime(filtros['desde'], '%Y-%m-%d')
            query = query.filter(Deteccion.created_at >= fecha_desde)
        except Exception:
            pass
    if filtros['hasta']:
        try:
            fecha_hasta = datetime.strptime(filtros['hasta'], '%Y-%m-%d')
            fecha_hasta = fecha_hasta.replace(hour=23, minute=59, second=59)
            query = query.filter(Deteccion.created_at <= fecha_hasta)
        except Exception:
            pass
    if filtros['solo']:
        query = query.filter(Deteccion.insect.isnot(None))

    # === Total ===
    total = query.count()

    # === Paginación compatible (SQLAlchemy <3 y >=3) ===
    try:
        items_paginados = db.paginate(
            query.order_by(Deteccion.created_at.desc()),
            page=page, per_page=per_page, error_out=False
        )
    except Exception:
        items_paginados = query.order_by(Deteccion.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

    # === Preparar datos ===
    items_formateados = []
    for d in items_paginados.items:
        items_formateados.append({
            'id': d.id,
            'fecha': d.created_at.strftime('%Y-%m-%d %H:%M:%S') if d.created_at else '--',
            'user': {'camera_name': d.camera_name or 'N/A'},
            'insecto_detectado': d.insect or 'Sin detección',
            'nombre_archivo': d.filename or '',
            'processed_filename': getattr(d, 'processed_filename', None),
            'temperature': d.temperature,
            'humidity': d.humidity,
            'enviado_telegram': getattr(d, 'enviado_telegram', False)
        })

    # === Cards estadísticas ===
    ultima = Deteccion.query.order_by(Deteccion.created_at.desc()).first()
    temp_actual = ultima.temperature if ultima else None
    hum_actual = ultima.humidity if ultima else None

    hoy_inicio = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    total_hoy = Deteccion.query.filter(Deteccion.created_at >= hoy_inicio).count()

    try:
        total_telegram = Deteccion.query.filter_by(enviado_telegram=True).count()
    except Exception:
        total_telegram = 0

    # === Conteo por insecto (para resumen) ===
    try:
        conteo = [
            (value or "Sin detección", total)
            for value, total in db.session.query(
                Deteccion.insect, func.count(Deteccion.id)
            ).group_by(Deteccion.insect).order_by(func.count(Deteccion.id).desc())
        ]
    except Exception as e:
        print("⚠️ Error generando conteo:", e)
        conteo = []

    # === Listas para filtros ===
    insectos = [
        value for value, in db.session.query(Deteccion.insect)
        .distinct().filter(Deteccion.insect.isnot(None)).order_by(Deteccion.insect)
    ]
    cams = [
        value for value, in db.session.query(Deteccion.camera_name)
        .distinct().filter(Deteccion.camera_name.isnot(None)).order_by(Deteccion.camera_name)
    ]

    return render_template('detecciones.html',
        items=items_formateados,
        total=total,
        page=page,
        per_page=per_page,
        filtros=filtros,
        insectos=insectos,
        cams=cams,
        temp_actual=temp_actual,
        hum_actual=hum_actual,
        total_hoy=total_hoy,
        total_telegram=total_telegram,
        conteo=conteo
    )


# ==============================================
# RESTO DE RUTAS
# ==============================================
@main_bp.route("/galeria")
@login_required
def galeria():
    registros = Deteccion.query.order_by(Deteccion.created_at.desc()).all()
    imagenes = [{
        "filename": r.filename,
        "processed_filename": getattr(r, 'processed_filename', None),
        "insecto": r.insect or "Sin detección",
        "confidence": r.confidence,
        "fecha": r.created_at,
    } for r in registros]
    return render_template("galeria.html", imagenes=imagenes)


@main_bp.route("/recomendacion")
@login_required
def recomendacion():
    mas_frec = db.session.query(
        Deteccion.insect, func.count(Deteccion.id)
    ).filter(Deteccion.insect.isnot(None)).group_by(
        Deteccion.insect
    ).order_by(func.count(Deteccion.id).desc()).first()

    if not mas_frec:
        return render_template("recomendacion.html",
                               mensaje="No existen detecciones registradas.")

    insecto, total = mas_frec
    info = _RECOMENDACIONES.get(insecto, {
        "nombre": insecto.replace("_", " ").title(),
        "descripcion": "No hay información detallada disponible.",
        "accion": "Revisar trampas y seguir protocolo general."
    })
    recomendacion = {
        "insecto": info["nombre"],
        "descripcion": info["descripcion"],
        "accion": info["accion"],
        "total": total,
    }
    return render_template("recomendacion.html", recomendacion=recomendacion)


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main_bp.detecciones"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        usuario = Usuario.query.filter_by(username=username).first()
        if usuario and usuario.password == password:
            login_user(usuario)
            destino = request.args.get("next")
            if _is_safe_next(destino):
                return redirect(destino)
            return redirect(url_for("main_bp.detecciones"))
        flash("Credenciales inválidas.", "danger")

    return render_template("login.html")


@main_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada correctamente.", "success")
    return redirect(url_for("main_bp.login"))


@main_bp.route("/imagenes/<path:filename>")
@login_required
def imagenes(filename: str):
    located = _locate_file(filename)
    if not located:
        abort(404)
    directory, safe_name = located
    return send_from_directory(directory, safe_name, as_attachment=False)


@main_bp.route("/imagen/<int:det_id>")
@login_required
def imagen_by_id(det_id: int):
    deteccion = Deteccion.query.get_or_404(det_id)
    if not deteccion.filename:
        abort(404)
    located = _locate_file(deteccion.filename)
    if not located:
        abort(404)
    directory, safe_name = located
    return send_from_directory(directory, safe_name, as_attachment=False)

@main_bp.route("/api/series")
def api_series():
    metric = request.args.get("metric")
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")
    cam = request.args.get("cam")
    insecto = request.args.get("insecto")

    if metric not in ("temperature", "humidity", "detections"):
        return jsonify({"error": "Invalid metric"}), 400
    if not desde or not hasta:
        return jsonify({"error": "Missing date range"}), 400

    try:
        d1 = datetime.strptime(desde, "%Y-%m-%d")
        d2 = datetime.strptime(hasta, "%Y-%m-%d")
        d2_end = d2 + timedelta(days=1)
    except ValueError:
        return jsonify({"error": "Invalid date format, use YYYY-MM-DD"}), 400

    q = Deteccion.query.filter(
        Deteccion.created_at >= d1,
        Deteccion.created_at < d2_end
    )

    if cam:
        q = q.filter(Deteccion.camera_name == cam)
    if insecto:
        q = q.filter(Deteccion.insect == insecto)

    if metric in ("temperature", "humidity"):
        col = Deteccion.temperature if metric == "temperature" else Deteccion.humidity
        rows = (
            q.with_entities(Deteccion.created_at, col)
             .order_by(Deteccion.created_at.asc())
             .all()
        )
        series = []
        for tstamp, val in rows:
            if val is None:
                continue
            series.append({"t": tstamp.isoformat(), "v": float(val)})
        return jsonify({"series": series})

    results = (
        db.session.query(func.date(Deteccion.created_at), func.count(Deteccion.id))
        .filter(Deteccion.created_at >= d1, Deteccion.created_at < d2_end)
        .filter(*( [Deteccion.camera_name == cam] if cam else [] ))
        .filter(*( [Deteccion.insect == insecto] if insecto else [] ))
        .group_by(func.date(Deteccion.created_at))
        .order_by(func.date(Deteccion.created_at))
        .all()
    )
    series = [{"t": str(day), "v": int(total)} for day, total in results]
    return jsonify({"series": series})