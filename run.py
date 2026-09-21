import os
import sys
import warnings
import threading
import time
from dotenv import load_dotenv

# Suprimir warnings de librerías externas (PyTorch y EasyOCR)
warnings.filterwarnings("ignore", category=UserWarning, module="torch")
warnings.filterwarnings("ignore", message=".*Using CPU.*")
warnings.filterwarnings("ignore", message=".*quantize_per_tensor.*")

# Forzar UTF-8 en stdout para evitar errores de encoding con emojis en Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Cargar el .env antes que todo
load_dotenv()

from app import create_app
from app.services.email_service import fetch_and_process_emails


def bg_email_task(app_context):
    """Tarea en segundo plano que revisa correos periódicamente."""
    with app_context.app_context():
        while True:
            try:
                print("\n[STOD Auto] 📧 Revisando la bandeja de entrada de Exchange...")
                fetch_and_process_emails()
            except Exception as e:
                print(f"[STOD Auto] ❌ Error en el servicio de correo: {str(e)}")
            time.sleep(60)  # Revisar cada 60 segundos


app = create_app()

# Arrancar el revisor de correos en segundo plano (siempre, no solo en __main__)
email_thread = threading.Thread(target=bg_email_task, args=(app,), daemon=True, name='EmailPoller')
email_thread.start()

if __name__ == '__main__':
    # use_reloader=False evita que Flask reinicie y lance dos hilos de correo
    app.run(host='0.0.0.0', port=5002, debug=True, use_reloader=False)
