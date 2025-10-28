from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urljoin, urlparse

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func

from core.config import Config
from core.database import db
from models.models import Deteccion, Usuario


main_bp = Blueprint("main_bp", __name__)

_IMAGE_DIRS = [
    Path(Config.DETECTADAS_DIR),
    Path(Config.NODETECCION_DIR),
    Path(Config.CAPTURE_DIR),
]

_RECOMENDACIONES = {
    "mosca_del_olivo": "Aplicar monitoreo diario y revisar presencia de larvas en frutos.",
    "algodoncillo": "Realizar poda sanitaria y usar trampas cromaticas para reducir la poblacion.",
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
    return (
        test_url.scheme in ("http", "https")
        and ref_url.netloc == test_url.netloc
    )


@main_bp.route("/")
@login_required
def index():
    clase = request.args.get("clase", "").strip()

    query = Deteccion.query.order_by(Deteccion.created_at.desc())
    if clase == "sin":
        query = query.filter(Deteccion.insect.is_(None))
    elif clase:
        query = query.filter(Deteccion.insect == clase)

    registros = query.all()

    clases = [
        value
        for value, in db.session.query(Deteccion.insect)
        .filter(Deteccion.insect.isnot(None))
        .distinct()
        .order_by(Deteccion.insect)
    ]

    conteo = [
        (value, total)
        for value, total in db.session.query(
            Deteccion.insect, func.count(Deteccion.id)
        )
        .group_by(Deteccion.insect)
        .order_by(func.count(Deteccion.id).desc())
    ]

    datos = [
        {
            "fecha": registro.created_at,
            "insecto": registro.insect or "Sin deteccion",
            "filename": registro.filename,
            "confidence": registro.confidence,
        }
        for registro in registros
    ]

    return render_template(
        "index.html",
        datos=datos,
        conteo=conteo,
        clases=clases,
        clase_activa=clase,
    )


@main_bp.route("/galeria")
@login_required
def galeria():
    registros = Deteccion.query.order_by(Deteccion.created_at.desc()).all()
    imagenes = [
        {
            "filename": registro.filename,
            "insecto": registro.insect or "Sin deteccion",
            "fecha": registro.created_at,
        }
        for registro in registros
    ]
    return render_template("galeria.html", imagenes=imagenes)


@main_bp.route("/recomendacion")
@login_required
def recomendacion():
    mas_frecuente = (
        db.session.query(
            Deteccion.insect,
            func.count(Deteccion.id).label("total"),
        )
        .filter(Deteccion.insect.isnot(None))
        .group_by(Deteccion.insect)
        .order_by(func.count(Deteccion.id).desc())
        .first()
    )

    if not mas_frecuente:
        return render_template(
            "recomendacion.html",
            mensaje="No existen detecciones registradas.",
        )

    insecto, total = mas_frecuente
    recomendacion = {
        "insecto": insecto,
        "total": total,
        "texto": _RECOMENDACIONES.get(
            insecto,
            "Revisar trampas y seguir el protocolo general de campo.",
        ),
    }
    return render_template("recomendacion.html", recomendacion=recomendacion)


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main_bp.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        usuario = Usuario.query.filter_by(username=username).first()
        if usuario and usuario.password == password:
            login_user(usuario)
            destino = request.args.get("next")
            if _is_safe_next(destino):
                return redirect(destino)
            return redirect(url_for("main_bp.index"))

        flash("Credenciales invalidas. Revisa usuario y clave.", "danger")

    return render_template("login.html")


@main_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesion cerrada correctamente.", "success")
    return redirect(url_for("main_bp.login"))


@main_bp.route("/imagenes/<path:filename>")
@login_required
def imagenes(filename: str):
    located = _locate_file(filename)
    if not located:
        abort(404)

    directory, safe_name = located
    return send_from_directory(directory, safe_name, as_attachment=False)
