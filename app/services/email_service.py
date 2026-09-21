"""
Servicio de correo usando Microsoft Graph API.
Se encarga de:
  1. Conectarse a la bandeja de entrada vía Graph API.
  2. Leer correos no procesados.
  3. Validar que traigan Factura y Orden de Compra.
  4. Enviar alertas de rechazo al proveedor si falta documentación.
  5. Descargar los adjuntos válidos a una carpeta temporal.
"""
import logging
import os
import requests
from pathlib import Path

from app.services.graph_auth_service import GraphAuthService

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Extensiones de adjuntos que aceptamos para procesamiento
EXTENSIONES_VALIDAS = {'.pdf', '.xml', '.jpg', '.jpeg', '.png'}

import shutil
import base64
from datetime import datetime
from config import config
from app.services.ocr_service import extract_metadata_from_documents

env_config = config['default']

# Memoria para no repetir logs de correos ignorados en cada ciclo
_correos_ignorados_vistos = set()

def _get_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

def fetch_and_process_emails():
    """
    Punto de entrada principal del servicio de correo.
    Filtra por asunto, descarga adjuntos, llama al OCR, crea el árbol y mueve archivos.
    """
    try:
        log.info("Iniciando conexión con Microsoft Graph API...")
        auth = GraphAuthService()
        token = auth.obtener_token()
        base_url = auth.base_url
        filtro_asunto = getattr(env_config, 'EMAIL_SUBJECT_FILTER', 'tramite de contrseña')
        
        # Soportar múltiples motivos separados por comas
        filtros = [f.strip() for f in filtro_asunto.split(',')]
        search_query = " OR ".join([f'"{f}"' for f in filtros])

        # Buscar correos no leídos (sin usar $search para poder loguear todos los que entran)
        url = f"{base_url}/mailFolders/inbox/messages"
        params = {
            "$top": 50,
            "$filter": "isRead eq false",
            "$select": "id,subject,receivedDateTime,hasAttachments,from,isRead"
        }
        
        r = requests.get(url, headers=_get_headers(token), params=params, timeout=30)
        r.raise_for_status()
        mensajes_no_leidos = r.json().get("value", [])

        if not mensajes_no_leidos:
            return

        for msg in mensajes_no_leidos:
            msg_id = msg["id"]
            subject = msg.get("subject", "Sin asunto")
            
            # Verificamos si el asunto cumple con alguno de nuestros filtros
            subject_lower = subject.lower()
            cumple_filtro = False
            for f in filtros:
                if f.lower() in subject_lower:
                    cumple_filtro = True
                    break
                    
            if not cumple_filtro:
                if msg_id not in _correos_ignorados_vistos:
                    log.info(f"📧 Ignorado: '{subject}' (No es de contraseñas)")
                    _correos_ignorados_vistos.add(msg_id)
                continue
                
            # VERIFICACIÓN DE SEGURIDAD: Evitar duplicados en Base de Datos
            from app.models import db, EmailLog
            if EmailLog.query.filter_by(msg_id=msg_id).first():
                log.warning(f"⚠️ El correo '{subject}' ya está en la Base de Datos pero seguía marcado como No Leído. Marcándolo como leído y omitiendo...")
                # Intentar marcarlo como leído para que no vuelva a molestar
                patch_url = f"{base_url}/messages/{msg_id}"
                requests.patch(patch_url, headers=_get_headers(token), json={"isRead": True}, timeout=30)
                continue
                
            log.info(f"📧 Procesando correo válido: '{subject}'")
            
            if not msg.get("hasAttachments"):
                log.warning("El correo no tiene adjuntos. Ignorando.")
                continue
                
            # Descargar adjuntos
            adjuntos_url = f"{base_url}/messages/{msg_id}/attachments"
            r_att = requests.get(adjuntos_url, headers=_get_headers(token), timeout=30)
            r_att.raise_for_status()
            adjuntos = r_att.json().get("value", [])
            
            # Filtramos solo archivos válidos y que pesen más de 10KB (para ignorar firmas de correo e iconos, pero permitir PDFs nativos livianos)
            archivos_validos = [a for a in adjuntos if a.get("@odata.type") == "#microsoft.graph.fileAttachment" and os.path.splitext(a.get("name", ""))[1].lower() in EXTENSIONES_VALIDAS and a.get("size", 0) > 10000]
            
            if not archivos_validos:
                log.warning("No hay adjuntos válidos (PDFs) en el correo.")
                continue
                
            import tempfile
            
            # 1. Guardar en carpeta temporal LOCAL (Escenario Óptimo de Rendimiento)
            temp_dir = os.path.join(tempfile.gettempdir(), 'stod_temp', msg_id)
            os.makedirs(temp_dir, exist_ok=True)
            
            rutas_pdfs = []
            for att in archivos_validos:
                file_path = os.path.join(temp_dir, att["name"])
                content = base64.b64decode(att["contentBytes"])
                with open(file_path, "wb") as f:
                    f.write(content)
                rutas_pdfs.append(file_path)
            
            log.info(f"Se descargaron {len(rutas_pdfs)} adjuntos al directorio temporal.")
            
            # 2. Extraer datos con OCR
            metadata = extract_metadata_from_documents(rutas_pdfs)
            
            # --- EVALUAR ESTADO Y GUARDAR EN BD ---
            from app.models import db, EmailLog
            
            missing = []
            if metadata.get("OrdenCompra") == "OC_DESCONOCIDA":
                missing.append("Orden de Compra")
            if metadata.get("FacturaReferencia") == "FACTURA_DESCONOCIDA":
                missing.append("Factura")
                
            if len(missing) == 0:
                estado = "Aceptada"
                missing_str = None
            elif len(missing) == 1:
                estado = "Parcial"
                missing_str = f"Falta: {missing[0]}"
            else:
                estado = "Rechazada"
                missing_str = "Falta OC y Factura (Ilegible/No válido)"

            # Guardar en Base de Datos
            fecha_correo = datetime.fromisoformat(msg.get("receivedDateTime")[:19])
            sender_email = msg.get("from", {}).get("emailAddress", {}).get("address", "Desconocido")
            
            nuevo_log = EmailLog(
                msg_id=msg_id,
                sender=sender_email,
                subject=subject,
                date_received=fecha_correo,
                status=estado,
                missing_docs=missing_str,
                extracted_empresa=metadata.get("Empresa"),
                extracted_nit=metadata.get("NIT")
            )
            db.session.add(nuevo_log)
            db.session.commit()
            # --------------------------------------
            
            # 3. Crear árbol de carpetas
            # Empresa / Año / Mes-Día / NIT / Autorizador / OC
            mes_dia = f"{fecha_correo.month:02d}-{fecha_correo.day:02d}"
            
            ruta_final = os.path.join(
                env_config.STORAGE_FOLDER,
                metadata["Empresa"],
                str(fecha_correo.year),
                mes_dia,
                metadata["NIT"],
                metadata["Autorizador"],
                metadata["OrdenCompra"]
            )
            os.makedirs(ruta_final, exist_ok=True)
            
            # 4. Mover archivos a la ruta final (Evitando sobreescrituras estilo Windows)
            for pdf_path in rutas_pdfs:
                nombre_archivo = os.path.basename(pdf_path)
                nombre_base, extension = os.path.splitext(nombre_archivo)
                
                destino = os.path.join(ruta_final, nombre_archivo)
                
                # Si ya existe, le agregamos (1), (2), (3)...
                contador = 1
                while os.path.exists(destino):
                    nuevo_nombre = f"{nombre_base} ({contador}){extension}"
                    destino = os.path.join(ruta_final, nuevo_nombre)
                    contador += 1
                    
                shutil.move(pdf_path, destino)
                
            log.info(f"✅ Archivos movidos exitosamente a: {ruta_final} | Estado: {estado}")
            
            # 5. Marcar como leído en el servidor para no volver a procesarlo
            patch_url = f"{base_url}/messages/{msg_id}"
            requests.patch(patch_url, headers=_get_headers(token), json={"isRead": True}, timeout=30)
            log.info("✅ Correo marcado como LEÍDO en el buzón para no procesarlo de nuevo.")
            
            # Limpiar temporal local
            try:
                shutil.rmtree(temp_dir)
            except OSError:
                pass # Puede fallar si quedó bloqueado por el sistema

    except Exception as e:
        log.error("❌ Error procesando correos: %s", str(e), exc_info=True)
