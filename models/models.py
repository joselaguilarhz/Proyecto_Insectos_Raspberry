from datetime import datetime

from flask_login import UserMixin

from core.database import db


class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)


class Deteccion(db.Model):
    __tablename__ = 'deteccion'
    
    id = db.Column(db.Integer, primary_key=True)
    camera_name = db.Column(db.String(100))
    filename = db.Column(db.String(255))
    processed_filename = db.Column(db.String(255), nullable=True)  
    insect = db.Column(db.String(100))
    confidence = db.Column(db.Float)
    temperature = db.Column(db.Float)
    humidity = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    enviado_telegram = db.Column(db.Boolean, default=False)