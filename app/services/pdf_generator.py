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
    
    pdf.output(ruta_destino)
    return ruta_destino
