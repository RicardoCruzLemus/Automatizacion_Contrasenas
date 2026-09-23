import os
import logging
import easyocr
import re
from pdf2image import convert_from_path
import tempfile

log = logging.getLogger(__name__)

# Instanciar el lector de EasyOCR una vez para ahorrar tiempo
# Soporta inglés y español
try:
    reader = easyocr.Reader(['es', 'en'], gpu=False)
except Exception as e:
    log.warning(f"No se pudo inicializar EasyOCR (probablemente falten dependencias): {e}")
    reader = None

def _extract_text_from_pdf(pdf_path: str) -> str:
    """Convierte un PDF a imágenes y extrae el texto usando EasyOCR."""
    if not reader:
        return ""
        
    full_text = ""
    try:
        # Buscar poppler en la carpeta local del proyecto
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        poppler_path = os.path.join(base_dir, 'bin', 'poppler', 'poppler-24.07.0', 'Library', 'bin')
        
        # Si no lo encuentra local, asume que está en el PATH de Windows
        if not os.path.exists(poppler_path):
            poppler_path = None
            
        # Convertir PDF a lista de imágenes
        images = convert_from_path(pdf_path, dpi=200, poppler_path=poppler_path)
        
        for img in images:
            # EasyOCR puede tomar numpy arrays, convertir la imagen PIL
            import numpy as np
            img_np = np.array(img)
            
            # detail=0 devuelve solo la lista de textos sin las coordenadas
            result = reader.readtext(img_np, detail=0)
            full_text += " ".join(result) + " \n"
            
    except Exception as e:
        log.error(f"Error procesando OCR del PDF {pdf_path}: {e}")
        
    return full_text

def extract_metadata_from_documents(pdf_paths: list) -> dict:
    """
    Recibe una lista de rutas de PDFs (Factura, OC, etc).
    Procesa todos los PDFs y busca la metadata necesaria usando Expresiones Regulares.
    """
    metadata = {
        "Empresa": "EMPRESA_DESCONOCIDA",
        "NIT": "NIT_DESCONOCIDO",
        "Autorizador": "AUTORIZADOR_DESCONOCIDO",
        "OrdenCompra": "OC_DESCONOCIDA",
        "CodigoProveedor": "CODIGO_DESCONOCIDO",
        "FacturaReferencia": "FACTURA_DESCONOCIDA",
        "FacturaTotal": "TOTAL_DESCONOCIDO",
        "CondicionesPago": None
    }
    
    texto_total = ""
    file_mapping = {}
    
    for pdf_path in pdf_paths:
        log.info(f"Aplicando OCR a: {os.path.basename(pdf_path)}")
        texto_pdf = _extract_text_from_pdf(pdf_path)
        texto_total += texto_pdf + "\n"
        
        # Identificación rápida para renombrar
        texto_limpio = " ".join(texto_pdf.split())
        if re.search(r'Orden de compra n[uú]mero', texto_limpio, re.IGNORECASE):
            file_mapping[pdf_path] = "OC_TYPE"
        elif re.search(r'DOCUMENTO TRIBUTARIO|Factura No\.|Serie', texto_limpio, re.IGNORECASE):
            file_mapping[pdf_path] = "FAC_TYPE"

        
    # Limpiamos un poco el texto para facilitar regex
    texto_total_limpio = " ".join(texto_total.split())
    
    # LOG DE DIAGNÓSTICO: muestra el texto completo que leyó el OCR
    log.info(f"=== TEXTO OCR EXTRAÍDO (primeros 1000 chars) ===\n{texto_total_limpio[:1000]}\n=================================================")
    
    # -----------------------------------------------------
    # LÓGICA DE EXTRACCIÓN MEDIANTE REGEX (Basada en documentos reales)
    # -----------------------------------------------------
    
    # 1. NIT del Proveedor (Excluyendo el de Canella)
    todos_los_nits = re.findall(r'NIT[\s:.-]*([0-9]{4,12}-?[0-9Kk])', texto_total_limpio, re.IGNORECASE)
    for nit in todos_los_nits:
        nit_limpio = nit.upper().replace(' ', '')
        if nit_limpio not in ['32561-9', '325619']:
            metadata["NIT"] = nit_limpio
            break

    # 2. Código de Proveedor (Ej: P005843)
    match_codigo = re.search(r'C[oó]digo de Proveedor[\s:]*([A-Z0-9]+)', texto_total_limpio, re.IGNORECASE)
    if match_codigo:
        metadata["CodigoProveedor"] = match_codigo.group(1).upper()
            
    # 3. Orden de Compra (Ej: 44021194)
    match_oc = re.search(r'Orden de compra n[uú]mero[\s:]*([0-9]{6,12})', texto_total_limpio, re.IGNORECASE)
    if match_oc:
        metadata["OrdenCompra"] = match_oc.group(1).upper()
        
    # 4. Empresa (Ej: CANELLA S.A.)
    # Buscamos variaciones sin dos puntos para ser más flexibles
    match_empresa = re.search(r'Nombre\s*([A-Za-z0-9\s.,&]+?)\s*(?:Nit|Direccion|Dirección)', texto_total_limpio, re.IGNORECASE)
    if match_empresa:
        metadata["Empresa"] = match_empresa.group(1).strip().replace('/', '_')
    elif 'canella' in texto_total_limpio.lower():
        # Fallback seguro: Si menciona canella, asumimos que la empresa compradora es Canella S.A.
        metadata["Empresa"] = "CANELLA S.A."
        
    # 5. Autorizador (Búsqueda inteligente directamente desde la BD)
    # En lugar de depender de una expresión regular frágil, buscamos si el nombre
    # del empleado (que ya está registrado en la UI) existe en el PDF.
    from app.models import AuthorizerMap
    autorizadores_db = AuthorizerMap.query.all()
    
    autorizador_final = "AUTORIZADOR_DESCONOCIDO"
    for map_db in autorizadores_db:
        # Si "Laura Gomar" está en el texto del OCR...
        if map_db.persona.lower() in texto_total_limpio.lower():
            autorizador_final = map_db.autorizador_stod
            break
            
    if autorizador_final != "AUTORIZADOR_DESCONOCIDO":
        metadata["Autorizador"] = autorizador_final
    else:
        # Fallback: Intentar extraer el texto crudo por si no está en la BD
        match_aut = re.search(r'OC realizada por:\s*([A-Za-z\s-]+)', texto_total_limpio, re.IGNORECASE)
        if match_aut:
            metadata["Autorizador"] = match_aut.group(1).strip(' -').replace('/', '_')

    # 6. Referencia de Factura (Ej: 2363378614)
    match_factura = re.search(r'No\.\s*[:]*\s*([0-9]{5,20})', texto_total_limpio, re.IGNORECASE)
    if match_factura:
        metadata["FacturaReferencia"] = match_factura.group(1)

    # 7. Total de Factura (Ej: Q 1,000.00)
    match_total = re.search(r'TOTAL(?: EN LETRAS)?[\s:]*(?:Q\s*)?([0-9,]+\.[0-9]{2})', texto_total_limpio, re.IGNORECASE)
    if match_total:
        metadata["FacturaTotal"] = match_total.group(1)

    # 8. Condiciones de Pago (Ej: 15 días)
    match_condiciones = re.search(r'Condiciones de Pago\s*[:]*\s*(\d+)\s*d[ií]as', texto_total_limpio, re.IGNORECASE)
    if match_condiciones:
        metadata["CondicionesPago"] = match_condiciones.group(1)

    log.info(f"Metadata extraída: {metadata}")
    
    # Asignar nombres finales según la metadata extraída
    final_mapping = {}
    for path, doc_type in file_mapping.items():
        if doc_type == "OC_TYPE" and metadata.get("OrdenCompra") != "OC_DESCONOCIDA":
            final_mapping[path] = f"OC-{metadata['OrdenCompra']}.pdf"
        elif doc_type == "FAC_TYPE" and metadata.get("FacturaReferencia") != "FACTURA_DESCONOCIDA":
            final_mapping[path] = f"FAC-{metadata['FacturaReferencia']}.pdf"
            
    metadata["file_mapping"] = final_mapping
    return metadata
