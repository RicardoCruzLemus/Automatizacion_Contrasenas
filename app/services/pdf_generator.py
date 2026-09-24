import os
from fpdf import FPDF
from datetime import datetime

class ComprobantePDF(FPDF):
    def header(self):
        # Intentar cargar el logo si existe
        logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'logo80.png')
        if os.path.exists(logo_path):
            self.image(logo_path, 10, 8, 33)
        self.set_font('Arial', 'B', 15)
        self.cell(80)
        self.cell(30, 10, 'Contrasenas de Pago para Proveedores', 0, 0, 'C')
        self.ln(20)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Generado automaticamente el {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', 0, 0, 'C')

def generar_comprobante_pdf(ruta_destino, datos):
    """
    Genera un PDF con apariencia de formulario STOD usando fpdf2.
    `datos` es un diccionario con:
    - codigo_proveedor
    - nit
    - nombre
    - autorizador
    - fecha_cheque
    - condiciones_pago
    - forma_pago
    - moneda
    """
    pdf = ComprobantePDF()
    pdf.add_page()
    pdf.set_font("Arial", size=11)
    
    # helper para dibujar filas
    def draw_row(label, value):
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(50, 10, label, border=0)
        pdf.set_font("Arial", '', 10)
        # un pequeño recuadro para simular el input
        pdf.cell(140, 10, str(value) if value else '--Seleccione una opcion--', border=1, ln=1)
        pdf.ln(2)

    draw_row("Codigo Proveedor", datos.get("codigo_proveedor", ""))
    draw_row("NIT", datos.get("nit", ""))
    pdf.ln(5)
    
    draw_row("Nombre", datos.get("nombre", ""))
    draw_row("Autorizador", datos.get("autorizador", ""))
    draw_row("Fecha Cheque", datos.get("fecha_cheque", ""))
    draw_row("Condiciones de pago", datos.get("condiciones_pago", ""))
    draw_row("Forma de pago", datos.get("forma_pago", ""))
    draw_row("Moneda", datos.get("moneda", ""))
    
    # -----------------------------------------------------
    # SECCIÓN: Listado de Facturas
    # -----------------------------------------------------
    pdf.ln(10)
    
    # Título con fondo celeste
    pdf.set_fill_color(83, 192, 222) # Un color celeste parecido a Bootstrap Info
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(50, 8, "Listado de Facturas", border=0, ln=1, align='C', fill=True)
    
    pdf.set_text_color(0, 0, 0) # Volver a negro
    pdf.ln(3)
    
    # Cabeceras de tabla
    pdf.set_font("Arial", 'B', 9)
    # Dimensiones: Referencia (60), Total (60), Orden_De_Compra (70)
    pdf.cell(60, 8, "Referencia", border='B', align='C')
    pdf.cell(60, 8, "Total", border='B', align='C')
    pdf.cell(70, 8, "Orden_De_Compra", border='B', align='C', ln=1)
    
    # Fila de datos
    pdf.set_font("Arial", '', 9)
    ref = str(datos.get("factura_referencia", ""))
    tot = str(datos.get("factura_total", ""))
    oc = str(datos.get("orden_compra", ""))
    
    pdf.cell(60, 10, ref, border='B', align='C')
    pdf.cell(60, 10, tot, border='B', align='C')
    pdf.cell(70, 10, oc, border='B', align='C', ln=1)
    
    # Footer de totales
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(60, 8, "Totales:", border=0, align='R')
    pdf.cell(60, 8, f"Q{tot}", border=0, align='C', ln=1)
    
    pdf.output(ruta_destino)
    return ruta_destino
