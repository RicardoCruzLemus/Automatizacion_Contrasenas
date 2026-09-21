from app import create_app
from app.models import db, AuthorizerMap

mapeo_inicial = {
    "Melisa Rubio": "ASTRID VICTORIA PEÑA DIEGUEZ - ISUZU",
    "Emilio Solis": "CESAR DANIEL MAZARIEGOS MEZA - TALLER YAMAHA",
    "Hector Citalan": "CESAR DANIEL MAZARIEGOS MEZA - TALLER YAMAHA",
    "Jorge Toj": "CESAR DANIEL MAZARIEGOS MEZA - TALLER YAMAHA",
    "Henry Reyes": "CESAR DANIEL MAZARIEGOS MEZA - TALLER YAMAHA",
    "Cesar Villela": "Cesar Villela - SERVICIO TÉCNICO",
    "Gloria Palomo": "Diana Canella - GERENCIA SOLUCIONES TECNOLÓGICAS",
    "Diego Contreras": "Eduardo Ara - YAMAHA VENTAS",
    "Cindy Velasquez": "Eduardo Ara - YAMAHA VENTAS",
    "Sandra Barrientos": "Eduardo Ara - YAMAHA VENTAS",
    "Dina Garcia": "HENRI DAVID RUIZ AMBELIS - AUDITORIA",
    "Omar Latin": "HENRI DAVID RUIZ AMBELIS - AUDITORIA",
    "Myra Davila": "Heydi Julissa Leon - IMPORTACIONES",
    "Heydi Leon": "Heydi Julissa Leon - IMPORTACIONES",
    "Norma Arias": "Joan Mario Rivera - ADMINISTRACIÓN",
    "Luis Cardenas": "Joan Mario Rivera - ADMINISTRACIÓN",
    "Santiago Martinez": "Joan Mario Rivera - ADMINISTRACIÓN",
    "Ingrid Velasquez": "Jorge Muralles - DIST. CANON",
    "Nincy Ortiz": "JOSE ANTONIO JUAREZ MANCILLA - MERCADEO ISUZU",
    "Leslie Monzon": "JOSE ANTONIO JUAREZ MANCILLA - MERCADEO ISUZU",
    "Laura Gomar": "JOSE ANTONIO JUAREZ MANCILLA - MERCADEO ISUZU",
    "Celeste Mejia": "Jose Luis Nuñez - REPUESTOS",
    "Javier Bran": "Jose Luis Nuñez - REPUESTOS",
    "Cesar Anona": "Jose Luis Nuñez - REPUESTOS",
    "Luis Patzan": "Jose Luis Nuñez - REPUESTOS",
    "William Perez": "Jose Miguel Garcia - VENTAS RETAIL",
    "Estephanie Castro": "Jose Roberto Aguirre - GERENCIA FINANCIERA",
    "Norma Garcia": "Juan Manuel Soto - SOL. DE IMPRESIÓN DIGITAL",
    "Sandra Lorenzo": "Juan Manuel Soto - SOL. DE IMPRESIÓN DIGITAL",
    "Cecilia Higueros": "Leonel Alvarez - SERVICIO TÉCNICO",
    "Maybelin Rodriguez": "Leonel Alvarez - SERVICIO TÉCNICO",
    "Lissette Esquivel": "Lissette Arrecis - RECURSOS HUMANOS",
    "Alejandra Gonzalez": "Lissette Arrecis - RECURSOS HUMANOS",
    "Astrid Peña": "Mario Tamayac - ISUZU",
    "Carmen Berduo": "Marisol Recinos - GERENCIA FINANCIERA",
    "Barbara Mendez": "MARTHA NINETH PEREIRA FLORES - NEW-HOLAND-CONSTRUCCION",
    "Yesvi Elias": "MARTHA NINETH PEREIRA FLORES - NEW-HOLAND-CONSTRUCCION",
    "Nineth Pereira": "MARTHA NINETH PEREIRA FLORES - NEW-HOLAND-CONSTRUCCION",
    "Rosalio Lic": "Raul Hernández - INFORMATICA",
    "Jeshua Barillas": "Raul Hernández - INFORMATICA",
    "Lisbeth España": "Raul Veliz - CORPORATIVO",
    "Rene Cotto": "Rene Cotto - MOTUL",
    "Susel Serrano": "Rene Cotto - MOTUL",
    "Gustavo Cabrera": "Ricardo Escobedo - CREDITOS Y COBROS",
    "Rocio Roman": "ROCIO ALEJANDRA ROMAN LETONA - MERCADEO",
    "Maria Jose Sazo": "ROCIO ALEJANDRA ROMAN LETONA - MERCADEO",
    "Gustavo Castillo": "Sandra Loarca - CONTABILIDAD",
    "Sandra Loarca": "Sandra Loarca - CONTABILIDAD",
    "Gamaliel Pichiya": "Solange Tambasco - IMPORTACIONES",
    "Sandra Osorio": "Solange Tambasco - IMPORTACIONES",
    "Jose Contreras": "Solange Tambasco - IMPORTACIONES"
}

app = create_app()

with app.app_context():
    agregados = 0
    for persona, autorizador in mapeo_inicial.items():
        if not AuthorizerMap.query.filter_by(persona=persona).first():
            nuevo = AuthorizerMap(persona=persona, autorizador_stod=autorizador)
            db.session.add(nuevo)
            agregados += 1
    
    db.session.commit()
    print(f"Se agregaron {agregados} mapeos a la base de datos de manera exitosa.")
