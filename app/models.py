from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import pytz

db = SQLAlchemy()

def get_guatemala_time():
    """Helper para obtener la hora actual en Guatemala"""
    gt_timezone = pytz.timezone('America/Guatemala')
    return datetime.now(gt_timezone)

class AuthorizerMap(db.Model):
    __tablename__ = 'authorizer_map'
    
    id = db.Column(db.Integer, primary_key=True)
    persona = db.Column(db.String(100), unique=True, nullable=False)
    autorizador_stod = db.Column(db.String(200), nullable=False)
    
    def __repr__(self):
        return f"<AuthorizerMap {self.persona} -> {self.autorizador_stod}>"

class EmailLog(db.Model):
    __tablename__ = 'email_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    msg_id = db.Column(db.String(255), unique=True, nullable=False)
    sender = db.Column(db.String(150), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    date_received = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(50), nullable=False) # 'Aceptada', 'Parcial', 'Rechazada'
    missing_docs = db.Column(db.String(255), nullable=True) # Detalles de lo que falta
    extracted_empresa = db.Column(db.String(150), nullable=True)
    extracted_nit = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=get_guatemala_time)
    
    def __repr__(self):
        return f"<EmailLog {self.status} - {self.subject}>"
