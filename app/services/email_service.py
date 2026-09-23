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
import hashlib
from pathlib import Path

from app.services.graph_auth_service import GraphAuthService

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Extensiones de adjuntos que aceptamos para procesamiento
EXTENSIONES_VALIDAS = {'.pdf', '.xml', '.jpg', '.jpeg', '.png'}

import shutil
import base64
import re
from datetime import datetime, timedelta
from config import config
from app.services.ocr_service import extract_metadata_from_documents
from app.services.stod_db_service import StodDbService
from app.services.pdf_generator import generar_comprobante_pdf

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
        
        # Buscar correos no leídos (sin usar $search para poder loguear todos los que entran)
        url = f"{base_url}/mailFolders/inbox/messages"
        params = {
            "$top": 50,
            "$filter": "isRead eq false",
            "$select": "id,subject,bodyPreview,receivedDateTime,hasAttachments,from,isRead"
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
            
            # 2.5 Consultar datos reales de STOD (SQL Server) usando el NIT
            stod_db = StodDbService()
            datos_comprobante = {
                "nit": metadata.get("NIT", ""),
                "autorizador": metadata.get("Autorizador", "")
            }
            
            if metadata.get("NIT") and metadata.get("NIT") != "NIT_DESCONOCIDO":
                res_prov = stod_db.validar_proveedor_por_nit(metadata["NIT"], metadata.get("Empresa"))
                if res_prov.get("exito"):
                    datos_comprobante["nombre"] = res_prov["nombre_proveedor"]
                    datos_comprobante["codigo_proveedor"] = res_prov["codigo_proveedor"]
                    
                    # Ahora traemos condiciones y forma de pago
                    res_cond = stod_db.obtener_condiciones_por_codigo(res_prov["codigo_proveedor"], metadata.get("Empresa"))
                    if res_cond.get("exito"):
                        # Si el OCR leyó los días desde la OC (ej: 15), usar esos. Si no, usar los de la BD de STOD (ej: 30)
                        dias_ocr = metadata.get("CondicionesPago")
                        if dias_ocr:
                            cond_pago = f"{dias_ocr} dias"
                        else:
                            cond_pago = res_cond["dias_credito"]
                            
                        datos_comprobante["condiciones_pago"] = cond_pago
                        datos_comprobante["forma_pago"] = res_cond["forma_pago"]
                        
                        # --- CALCULAR FECHA DE CHEQUE (PRÓXIMO VIERNES) ---
                        # Fecha del correo (la parseamos primero porque la necesitamos aquí)
                        try:
                            fecha_correo = datetime.fromisoformat(msg.get("receivedDateTime")[:19])
                        except:
                            fecha_correo = datetime.now()
                            
                        # Extraer solo el número de días (ej: "30 dias" -> 30)
                        dias_credito = 0
                        if isinstance(cond_pago, int):
                            dias_credito = cond_pago
                        elif isinstance(cond_pago, str):
                            match_dias = re.search(r'\d+', cond_pago)
                            if match_dias:
                                dias_credito = int(match_dias.group(0))
                                
                        fecha_base = fecha_correo + timedelta(days=dias_credito)
                        
                        # Ajustar al viernes más próximo (Lunes=0, Viernes=4, Domingo=6)
                        weekday = fecha_base.weekday()
                        if weekday <= 4:
                            dias_para_viernes = 4 - weekday
                        else:
                            dias_para_viernes = (4 - weekday) + 7
                            
                        fecha_cheque = fecha_base + timedelta(days=dias_para_viernes)
                        datos_comprobante["fecha_cheque"] = fecha_cheque.strftime('%Y-%m-%d')
                        
                        # Mapear la moneda para que diga "Quetzales" o "Dolares" como en STOD
                        moneda_db = str(res_cond.get("moneda", "")).upper()
                        if "USD" in moneda_db or "DOLAR" in moneda_db:
                            datos_comprobante["moneda"] = "Dolares"
                        elif moneda_db: # Si hay algo y no es USD, asumimos Quetzales
                            datos_comprobante["moneda"] = "Quetzales"
                        else:
                            datos_comprobante["moneda"] = ""
            
            # --- EVALUAR ESTADO Y GUARDAR EN BD ---
            
            # Chequear indicador explícito de parcial en asunto o cuerpo
            subject_lower = msg.get("subject", "").lower()
            body_preview_lower = msg.get("bodyPreview", "").lower()
            is_explicit_parcial = "parcial" in subject_lower or "parcial" in body_preview_lower
            
            missing = []
            if metadata.get("OrdenCompra") == "OC_DESCONOCIDA":
                missing.append("Orden de Compra")
            if metadata.get("FacturaReferencia") == "FACTURA_DESCONOCIDA":
                missing.append("Factura")
                
            if len(missing) == 2:
                estado = "Rechazada"
                missing_str = "No se logró leer Factura ni OC"
            elif len(missing) == 1 or len(rutas_pdfs) == 1 or is_explicit_parcial:
                estado = "Parcial"
                if is_explicit_parcial:
                    missing_str = "Marcado como parcial en el correo"
                elif len(missing) == 1:
                    missing_str = f"Falta documento: {missing[0]}"
                else:
                    missing_str = "Solo trae 1 archivo adjunto"
            else:
                estado = "Aceptada"
                missing_str = None

            # Añadir "Aceptadas", "Parciales" o "Rechazadas" al folder principal
            estado_folder = estado + "s" if estado in ["Aceptada", "Rechazada"] else "Parciales"
            
            # Fecha del correo para la carpeta del año y para la BD (si no se parseó antes)
            try:
                fecha_correo = datetime.fromisoformat(msg.get("receivedDateTime")[:19])
            except:
                fecha_correo = datetime.now()
            
            # Empresa / Año / NIT-xxx / Autorizador / OC-xxx
            ruta_final = os.path.join(
                env_config.STORAGE_FOLDER,
                estado_folder,
                metadata["Empresa"],
                str(fecha_correo.year),
                f"NIT-{metadata['NIT']}",
                metadata["Autorizador"],
                f"OC-{metadata['OrdenCompra']}"
            )
            
            # Guardar en Base de Datos Local
            sender_email = msg.get("from", {}).get("emailAddress", {}).get("address", "Desconocido")
            
            nuevo_log = EmailLog(
                msg_id=msg_id,
                sender=sender_email,
                subject=subject,
                date_received=fecha_correo,
                status=estado,
                missing_docs=missing_str,
                extracted_empresa=metadata.get("Empresa"),
                extracted_nit=metadata.get("NIT"),
                file_path=ruta_final
            )
            db.session.add(nuevo_log)
            db.session.commit()
            # --------------------------------------
            os.makedirs(ruta_final, exist_ok=True)
            
            # 4. Mover archivos a la ruta final (Evitando duplicados exactos y sobreescrituras)
            
            # Helper para calcular el hash de un archivo
            def hash_file(filepath):
                hasher = hashlib.md5()
                try:
                    with open(filepath, 'rb') as f:
                        buf = f.read(65536)
                        while len(buf) > 0:
                            hasher.update(buf)
                            buf = f.read(65536)
                    return hasher.hexdigest()
                except Exception:
                    return None
                    
            # Obtener los hashes de los archivos que ya existen en la carpeta final
            hashes_existentes = set()
            if os.path.exists(ruta_final):
                for file_in_dir in os.listdir(ruta_final):
                    full_path_in_dir = os.path.join(ruta_final, file_in_dir)
                    if os.path.isfile(full_path_in_dir):
                        hashes_existentes.add(hash_file(full_path_in_dir))

            for pdf_path in rutas_pdfs:
                # Si el archivo nuevo es idéntico a uno que ya está, lo ignoramos
                nuevo_hash = hash_file(pdf_path)
                if nuevo_hash in hashes_existentes:
                    log.info(f"Omitiendo adjunto duplicado (ya existe en carpeta): {os.path.basename(pdf_path)}")
                    continue
                
                # Si es nuevo, lo guardamos. Aseguramos no sobreescribir si tienen el mismo nombre pero diferente contenido
                nombre_archivo_original = os.path.basename(pdf_path)
                
                # Usar el nombre renombrado (OC-xxx.pdf o FAC-xxx.pdf) si el OCR lo identificó
                mapping = metadata.get("file_mapping", {})
                nombre_archivo = mapping.get(pdf_path, nombre_archivo_original)
                
                nombre_base, extension = os.path.splitext(nombre_archivo)
                destino = os.path.join(ruta_final, nombre_archivo)
                
                contador = 1
                while os.path.exists(destino):
                    nuevo_nombre = f"{nombre_base} ({contador}){extension}"
                    destino = os.path.join(ruta_final, nuevo_nombre)
                    contador += 1
                    
                shutil.move(pdf_path, destino)
                # Agregamos el hash a los existentes por si vienen 2 idénticos en el MISMO correo
                hashes_existentes.add(nuevo_hash)

                
            log.info(f"✅ Archivos movidos exitosamente a: {ruta_final} | Estado: {estado}")
            
            # 5. Generar y Guardar el Comprobante PDF (Si fue aceptada/parcial)
            if estado in ["Aceptada", "Parcial"]:
                nombre_comprobante = f"Comprobante_STOD_{metadata['OrdenCompra']}.pdf"
                ruta_comprobante = os.path.join(ruta_final, nombre_comprobante)
                
                # Si el archivo ya existe, fpdf lo sobreescribirá automáticamente
                generar_comprobante_pdf(ruta_comprobante, datos_comprobante)
                log.info(f"📄 Comprobante PDF generado/actualizado exitosamente en: {ruta_comprobante}")
            
            # 6. Marcar como leído en el servidor para no volver a procesarlo
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
