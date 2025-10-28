from flask import Flask
from flask_login import LoginManager

from core.config import Config
from core.database import db
from models.models import Usuario
from routes.main_routes import main_bp
from routes.upload_routes import upload_bp


login_manager = LoginManager()


@login_manager.user_loader
def load_user(user_id: str):
    if not user_id:
        return None
    return Usuario.query.get(int(user_id))


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "main_bp.login"
    login_manager.login_message = "Inicia sesion para continuar."
    login_manager.login_message_category = "warning"

    with app.app_context():
        db.create_all()
        if not Usuario.query.filter_by(username=Config.DEFAULT_USERNAME).first():
            user = Usuario(
                username=Config.DEFAULT_USERNAME,
                password=Config.DEFAULT_PASSWORD,
            )
            db.session.add(user)
            db.session.commit()

    app.register_blueprint(main_bp)
    app.register_blueprint(upload_bp)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=8000, debug=True)
