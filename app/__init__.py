import os
import logging
import subprocess
from flask import Flask
from config import config

def _connect_network_drive(path, user, password, domain):
    """Intenta conectar a una ruta de red usando 'net use' con credenciales."""
    if not (user and password):
        return  # Sin credenciales, asume acceso libre o que ya está conectado
    
    # Extraer solo el host (\\IP) de la ruta completa
    parts = path.replace('\\\\', '').split('\\')
    host_path = f'\\\\{parts[0]}\\{parts[1]}' if len(parts) > 1 else f'\\\\{parts[0]}'
    
    user_str = f'{domain}\\{user}' if domain else user
    
    try:
        result = subprocess.run(
            ['net', 'use', host_path, password, f'/user:{user_str}', '/persistent:no'],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            logging.info(f'✅ Conectado a recurso de red: {host_path}')
        else:
            logging.warning(f'⚠️ net use falló (puede que ya esté conectado): {result.stderr.strip()}')
    except Exception as e:
        logging.warning(f'⚠️ No se pudo ejecutar net use: {e}')


def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Aseguramos que la carpeta de almacenamiento exista (si la ruta de red no está disponible, solo advertimos)
    import logging
    try:
        # Si es ruta de red y hay credenciales, conectar primero
        storage = app.config['STORAGE_FOLDER']
        if storage.startswith('\\\\') or storage.startswith('//'):
            _connect_network_drive(
                storage,
                app.config.get('SERVER_USERNAME', ''),
                app.config.get('SERVER_PASSWORD', ''),
                ''  # Sin dominio por defecto, solo usuario local del servidor
            )
        os.makedirs(storage, exist_ok=True)
    except OSError as e:
        logging.warning(f"⚠️ No se pudo crear/acceder a STORAGE_FOLDER '{app.config['STORAGE_FOLDER']}': {e}. Los archivos se guardarán en 'storage/' local hasta que la red esté disponible.")
        # Fallback a carpeta local
        local_storage = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'storage')
        os.makedirs(local_storage, exist_ok=True)
        app.config['STORAGE_FOLDER'] = local_storage

    # Inicializar Base de Datos
    from app.models import db
    db.init_app(app)
    with app.app_context():
        db.create_all()

    # Registro de Blueprints (Vistas y APIs)
    from app.views.panel_views import panel_bp
    app.register_blueprint(panel_bp)
    
    from app.api.endpoints import api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    return app
