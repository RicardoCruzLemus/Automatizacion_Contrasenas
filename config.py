import os

class Config:
    """Configuración base"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'una_clave_secreta_muy_segura'
    
    # Credenciales de Correo (Microsoft Exchange EWS)
    EXCHANGE_EMAIL = os.environ.get('EXCHANGE_EMAIL', 'tu_correo@dominio.com')
    EXCHANGE_PASSWORD = os.environ.get('EXCHANGE_PASSWORD', 'tu_password')
    EXCHANGE_SERVER = os.environ.get('EXCHANGE_SERVER', 'owa.canella.com.gt')

    # Configuración de base de datos y rutas de guardado
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    STORAGE_FOLDER = os.environ.get('STORAGE_FOLDER', os.path.join(BASE_DIR, 'storage'))
    TEMP_FOLDER = os.environ.get('TEMP_FOLDER', None)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///' + os.path.join(BASE_DIR, 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Filtro de correo
    EMAIL_SUBJECT_FILTER = os.environ.get('EMAIL_SUBJECT_FILTER', 'tramite de contrseña')
    
    # Credenciales del servidor de archivos (para carpetas compartidas de red)
    SERVER_IP = os.environ.get('SERVER_IP', '')
    SERVER_USERNAME = os.environ.get('SERVER_USERNAME', '')
    SERVER_PASSWORD = os.environ.get('SERVER_PASSWORD', '')
    
class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
