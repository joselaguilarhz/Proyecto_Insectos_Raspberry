#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
import click
import secrets
from datetime import datetime

from flask import (
    Flask, render_template, request,
    url_for, redirect, flash, current_app, jsonify,
    send_from_directory, abort
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin,
    login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import func, text

# --------- Configuration ---------
app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-me')

# Usa el mismo archivo de BD que tu script de captura (ENV DB_PATH) o cae en app.db
DB_PATH = os.environ.get('DB_PATH', os.path.join(app.root_path, 'app.db'))
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{DB_PATH}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Carpeta donde se guardarán las imágenes subidas por /upload
UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Directorios gestionados por el capturador (desde .env), para poder servir imágenes
CAPTURE_DIR     = os.environ.get('CAPTURE_DIR', '/home/smartfenix/fotos_cam/entrantes')
DETECTADAS_DIR  = os.environ.get('DETECTADAS_DIR', '/home/smartfenix/fotos_cam/detectadas')
NODETECCION_DIR = os.environ.get('NODETECCION_DIR', '/home/smartfenix/fotos_cam/nodeteccion')

# Inicializamos SQLAlchemy con la app
db = SQLAlchemy(app)

# --------- Logging ---------
app.logger.setLevel(logging.DEBUG)

# --------- Modelos ---------
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80), nullable=False)
    camera_name   = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False, default='')  # añadida por migración si falta
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    detecciones   = db.relationship('Deteccion', back_populates='user', cascade='all,delete-orphan')

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, pw)

class Deteccion(db.Model):
    __tablename__ = 'detecciones'
    id               = db.Column(db.Integer, primary_key=True)
    user_id          = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    nombre_archivo   = db.Column(db.String(255))
    insecto_detectado= db.Column(db.String(80))
    fecha            = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    ruta_imagen      = db.Column(db.String(1024))
    enviado_telegram = db.Column(db.Boolean, default=False)

    user             = db.relationship('User', back_populates='detecciones')

# --------- Migración ligera (SQLite) ---------
def _table_columns(table_name: str):
    rows = db.session.execute(text(f"PRAGMA table_info('{table_name}')")).all()
    return {r[1] for r in rows}  # set de nombres de columnas

def migrate_schema_if_needed():
    """
    Añade columnas que falten en tablas existentes (compat con BD creada por sqlite3 “puro”).
    Debe ejecutarse ANTES de cualquier query ORM que use esas columnas.
    """
    conn = db.engine.connect()
    insp_users = conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    if insp_users:
        cols_users = _table_columns('users')
        if 'password_hash' not in cols_users:
            app.logger.warning("[MIGRATION] Añadiendo columna users.password_hash")
            db.session.execute(text("ALTER TABLE users ADD COLUMN password_hash TEXT DEFAULT ''"))
        if 'created_at' not in cols_users:
            app.logger.warning("[MIGRATION] Añadiendo columna users.created_at")
            db.session.execute(text("ALTER TABLE users ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        db.session.commit()

    insp_det = conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='detecciones'"
    ).fetchone()
    if insp_det:
        # Crear índice si no existe
        app.logger.info("[MIGRATION] Creando índice ix_detecciones_fecha si no existía")
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_detecciones_fecha ON detecciones (fecha)"))
        db.session.commit()
    conn.close()

# --------- Crear usuario por defecto ---------
def ensure_default_user():
    """
    Crea un usuario por defecto si no existe uno con el CAMERA_NAME indicado.
    Idempotente.
    """
    camera_name = os.environ.get('CAMERA_NAME', 'camara-finca').strip()
    username = os.environ.get('DEFAULT_USERNAME', 'admin').strip()
    password = os.environ.get('DEFAULT_PASSWORD', 'admin123').strip()

    existing = User.query.filter_by(camera_name=camera_name).first()
    if existing:
        app.logger.info(
            f"[AUTO-USER] Ya existe usuario para CAMERA_NAME='{camera_name}' "
            f"(id={existing.id}, username='{existing.username}')."
        )
        return

    if not username:
        username = f"admin_{secrets.token_hex(3)}"
    if not password:
        password = secrets.token_urlsafe(10)

    u = User(username=username, camera_name=camera_name)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()

    app.logger.warning(
        f"[AUTO-USER] Usuario creado automáticamente: "
        f"username='{username}', password='{password}', camera_name='{camera_name}', id={u.id}"
    )

# --------- Inicialización ---------
with app.app_context():
    migrate_schema_if_needed()   # 1) migrar si hace falta
    db.create_all()              # 2) crear tablas que falten
    ensure_default_user()        # 3) asegurar usuario por defecto
    app.logger.info(f"BD inicializada en: {DB_PATH}")

# --------- CLI ---------
@app.cli.command('create-user')
@click.argument('username')
@click.argument('password')
@click.argument('camera_name')
def create_user(username, password, camera_name):
    """Crea un usuario con USERNAME, PASSWORD y nombre de cámara."""
    if User.query.filter_by(username=username).first():
        click.echo(f"Usuario '{username}' ya existe.")
        return
    if User.query.filter_by(camera_name=camera_name).first():
        click.echo(f"La cámara '{camera_name}' ya está asignada.")
        return
    u = User(username=username, camera_name=camera_name)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    click.echo(f"Usuario '{username}' (cámara: {camera_name}) creado con id={u.id}.")

@app.cli.command('reset-user')
@click.argument('camera_name')
@click.argument('username')
@click.argument('password')
def reset_user(camera_name, username, password):
    """
    Sobrescribe username y password del usuario con esa cámara.
    Si no existe, lo crea.
    """
    u = User.query.filter_by(camera_name=camera_name).first()
    if not u:
        click.echo(f"No existe usuario con camera_name='{camera_name}'. Creándolo...")
        u = User(username=username, camera_name=camera_name)
    else:
        u.username = username
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    click.echo(f"OK: camera='{camera_name}', username='{username}' actualizado/creado (id={u.id}).")

# --------- Login Setup ---------
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(uid):
    return db.session.get(User, int(uid))

# --------- Rutas de autenticación ---------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(request.args.get('next') or url_for('index'))
    next_page = request.args.get('next')
    if request.method == 'POST':
        u = User.query.filter_by(username=request.form['username']).first()
        if u and u.check_password(request.form['password']):
            login_user(u)
            return redirect(request.form.get('next') or url_for('index'))
        flash('Credenciales inválidas.')
    return render_template('login.html', next=next_page)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --------- Global detection logic ---------
CLASES = [
    "abeja", "algodoncillo", "arana", "barrenillo_de_olivo", "cabezudo_almendro",
    "cochinilla_negra_del_olivo", "Euzophera", "Glifodes", "hormiga", "mariquita",
    "mosca_del_olivo", "polilla_del_olivo"
]
RECOMENDACIONES = {
    "abeja": "No aplicar insecticidas (polinizador).",
    "algodoncillo": "Aceite de parafina 1% o jabón potásico.",
    "arana": "Control biológico. Evitar insecticidas.",
    "barrenillo_de_olivo": "Clorpirifos 48% o diflubenzurón.",
    "cabezudo_almendro": "Spinosad o emamectina en brotación.",
    "cochinilla_negra_del_olivo": "Aceite mineral + piriproxifén o jabón potásico.",
    "Euzophera": "Spinosad o B. thuringiensis antes del verano.",
    "Glifodes": "B. thuringiensis o spinosad.",
    "hormiga": "Cebo con fipronil o imidacloprid.",
    "mariquita": "No tratar (beneficioso).",
    "mosca_del_olivo": "Deltametrina o spinosad en cebo.",
    "polilla_del_olivo": "B. thuringiensis o lambda-cihalotrina."
}

# --------- Vistas protegidas ---------
@app.route('/')
@login_required
def index():
    q = Deteccion.query.filter_by(user_id=current_user.id)
    act = request.args.get('clase')
    if act:
        if act == 'sin':
            q = q.filter(Deteccion.insecto_detectado.is_(None))
        else:
            q = q.filter(Deteccion.insecto_detectado == act)
    datos = q.order_by(Deteccion.fecha.desc()).limit(200).all()
    count = (
        db.session.query(Deteccion.insecto_detectado, func.count())
                  .filter(Deteccion.user_id == current_user.id)
                  .group_by(Deteccion.insecto_detectado)
                  .order_by(func.count().desc()).all()
    )
    return render_template('index.html', datos=datos, clases=CLASES, clase_activa=act, conteo=count)

@app.route('/recomendacion')
@login_required
def recomendacion():
    cnt = (
        db.session.query(Deteccion.insecto_detectado, func.count())
                  .filter(Deteccion.user_id == current_user.id)
                  .group_by(Deteccion.insecto_detectado)
                  .order_by(func.count().desc()).all()
    )
    if not cnt:
        return render_template('recomendacion.html', recomendacion=None, mensaje="No hay detecciones aún.")
    insecto, total = cnt[0]
    text = RECOMENDACIONES.get(insecto, "Sin recomendación.")
    return render_template('recomendacion.html', recomendacion={'insecto': insecto, 'total': total, 'texto': text}, mensaje=None)

# --------- Servir imágenes ---------
# --------- Servir imagenes (robusto) ---------
@app.route('/imagenes/<path:filename>')
@login_required
def imagenes(filename):
    """
    Acepta:
      - 'nombre.jpg'
      - 'nodeteccion/nombre.jpg'
      - 'detectadas/nombre.jpg'
      - 'entrantes/nombre.jpg'
      - rutas absolutas (si caen dentro de los directorios permitidos)
    """
    # Bases permitidas
    bases = [
        app.config['UPLOAD_FOLDER'],
        DETECTADAS_DIR,
        NODETECCION_DIR,
        CAPTURE_DIR,
    ]

    # Normaliza
    filename = filename.strip("/")
    head, tail = os.path.split(filename)  # head puede ser 'nodeteccion', 'detectadas', etc.

    # 1) Si viene ruta absoluta y est� dentro de alguna base, servirla
    if os.path.isabs(filename) and os.path.isfile(filename):
        for base in bases:
            try:
                if os.path.commonpath([os.path.realpath(filename), os.path.realpath(base)]) == os.path.realpath(base):
                    return send_from_directory(os.path.dirname(filename), os.path.basename(filename))
            except Exception:
                pass  # por si commonpath falla con paths raros

    # 2) Si viene con prefijo de carpeta logica, mapealo
    prefix_map = {
        "nodeteccion": NODETECCION_DIR,
        "detectadas": DETECTADAS_DIR,
        "entrantes":  CAPTURE_DIR,
        "uploads":    app.config['UPLOAD_FOLDER'],
    }
    candidates = []

    if head in prefix_map:
        candidates.append(os.path.join(prefix_map[head], tail))

    # 3) Siempre probar a buscar por el basename en todas las bases
    basename = tail if tail else filename
    for base in bases:
        candidates.append(os.path.join(base, basename))

    # 4) Devolver el primero que exista
    for path in candidates:
        if os.path.isfile(path):
            return send_from_directory(os.path.dirname(path), os.path.basename(path))

    current_app.logger.warning(f"[IMAGENES] No encontrado: {filename} -> {candidates}")
    abort(404)

# --------- Galera ---------

@app.route("/galeria")
@login_required
def galeria():
    imagenes = Deteccion.query.order_by(Deteccion.fecha.desc()).limit(50).all()
    return render_template("galeria.html", imagenes=imagenes)


# --------- Endpoint de subida ---------
@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files or 'camera_name' not in request.form:
        return jsonify({"status": "error", "message": "Falta file o camera_name"}), 400

    file = request.files['file']
    camera_name = request.form['camera_name'].strip()
    if not file or file.filename == '' or not camera_name:
        return jsonify({"status": "error", "message": "file vacío o camera_name inválido"}), 400

    user = User.query.filter_by(camera_name=camera_name).first()
    if not user:
        return jsonify({"status": "error", "message": f"Cámara '{camera_name}' no registrada"}), 400

    filename = secure_filename(f"{camera_name}_{int(datetime.utcnow().timestamp())}_{file.filename}")
    path_img = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    try:
        file.save(path_img)
    except Exception as e:
        current_app.logger.error(f"No pude guardar {path_img}: {e}")
        return jsonify({"status": "error", "message": "Error al guardar fichero"}), 500

    insect = 'placeholder'
    det = Deteccion(
        user_id=user.id,
        nombre_archivo=filename,
        insecto_detectado=insect,
        ruta_imagen=path_img,
        enviado_telegram=False,
        fecha=datetime.utcnow()
    )
    try:
        db.session.add(det)
        db.session.commit()
        return jsonify({"status": "ok", "insect": insect}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Error en base de datos")
        return jsonify({"status": "error", "message": "Error en base de datos"}), 500

# --------- Run ---------
if __name__=='__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
