import logging
import pyodbc
from config import config

env_config = config['default']
log = logging.getLogger(__name__)

class StodDbService:
    def __init__(self):
        self.server = env_config.STOD_DB_SERVER
        self.database = env_config.STOD_DB_NAME
        self.username = env_config.STOD_DB_USER
        self.password = env_config.STOD_DB_PASSWORD
        
    def _get_connection(self):
        conn_str = f"DRIVER={{SQL Server}};SERVER={self.server};DATABASE={self.database};UID={self.username};PWD={self.password}"
        return pyodbc.connect(conn_str, timeout=10)

    def obtener_empresas(self):
        """
        Obtiene el catálogo de empresas desde CPRO_Empresa.
        Retorna un diccionario mapeando Nombre de la empresa -> Id_Empresa
        """
        empresas = {}
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT Id_Empresa, Nombre FROM CPRO_Empresa")
                for row in cursor.fetchall():
                    # Usamos .upper() para facilitar las coincidencias luego
                    empresas[row.Nombre.strip().upper()] = row.Id_Empresa
        except Exception as e:
            log.error(f"Error obteniendo empresas de STOD: {e}")
        return empresas

    def buscar_id_empresa(self, nombre_empresa_ocr):
        """
        Intenta buscar el Id_Empresa (Ej. 1 para Canella S.A.)
        basándose en el nombre que extrajo el OCR.
        Si no la encuentra con certeza, devuelve 1 por defecto.
        """
        if not nombre_empresa_ocr or nombre_empresa_ocr == "EMPRESA_DESCONOCIDA":
            return 1 # Default Canella
            
        empresas = self.obtener_empresas()
        
        ocr_upper = nombre_empresa_ocr.upper()
        
        # Búsqueda exacta
        if ocr_upper in empresas:
            return empresas[ocr_upper]
            
        # Búsqueda parcial (Ej. si OCR dice "CANELLA" y en la BD dice "CANELLA S.A.")
        for nombre_db, id_emp in empresas.items():
            if nombre_db in ocr_upper or ocr_upper in nombre_db:
                return id_emp
                
        return 1 # Fallback a Canella

    def validar_proveedor_por_nit(self, nit, nombre_empresa_ocr):
        """
        Llama al SP: CPRO_ValidarProveedor
        Devuelve el Nombre del proveedor (STOD_Mensaje), su Código, y la Empresa.
        """
        id_empresa = self.buscar_id_empresa(nombre_empresa_ocr)
        usuario_robot = 'ROBOT_STOD'
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Preparamos las variables OUTPUT
                sql = """
                DECLARE @MensajeTipo INT;
                DECLARE @MensajeDescripcion VARCHAR(200);
                
                EXEC CPRO_ValidarProveedor 
                    @NIT = ?, 
                    @IDEMPRESA = ?, 
                    @Usuario = ?, 
                    @MensajeTipo = @MensajeTipo OUTPUT, 
                    @MensajeDescripcion = @MensajeDescripcion OUTPUT;
                """
                
                # 1. Intentar con el NIT exacto (como viene del OCR)
                cursor.execute(sql, (nit, id_empresa, usuario_robot))
                row = cursor.fetchone()
                if row and row.STOD_Mensaje and row.STOD_Mensaje.strip() != "":
                    return {
                        "exito": True,
                        "nombre_proveedor": row.STOD_Mensaje,
                        "codigo_proveedor": row.Codigo
                    }
                
                # Si falló, limpiamos el NIT quitando cualquier espacio o símbolo raro
                nit_limpio = "".join(c for c in nit if c.isalnum())
                
                if nit_limpio:
                    # 2. Intentar con el NIT completamente limpio (sin guiones)
                    cursor.execute(sql, (nit_limpio, id_empresa, usuario_robot))
                    row2 = cursor.fetchone()
                    if row2 and row2.STOD_Mensaje and row2.STOD_Mensaje.strip() != "":
                        return {
                            "exito": True,
                            "nombre_proveedor": row2.STOD_Mensaje,
                            "codigo_proveedor": row2.Codigo
                        }

                    # 3. Intentar con el NIT en formato estándar guatemalteco (un guion antes del último dígito)
                    if len(nit_limpio) > 1:
                        nit_estandar = nit_limpio[:-1] + "-" + nit_limpio[-1]
                        cursor.execute(sql, (nit_estandar, id_empresa, usuario_robot))
                        row3 = cursor.fetchone()
                        if row3 and row3.STOD_Mensaje and row3.STOD_Mensaje.strip() != "":
                            return {
                                "exito": True,
                                "nombre_proveedor": row3.STOD_Mensaje,
                                "codigo_proveedor": row3.Codigo
                            }

                return {"exito": False, "error": "Proveedor no encontrado o inactivo en STOD."}
                    
        except Exception as e:
            log.error(f"Error en validar_proveedor_por_nit: {e}")
            return {"exito": False, "error": str(e)}

    def obtener_condiciones_por_codigo(self, codigo, nombre_empresa_ocr):
        """
        Llama al SP: CPRO_ObtenerDiasPagoCode
        Devuelve Días de crédito y Forma de pago.
        """
        id_empresa = self.buscar_id_empresa(nombre_empresa_ocr)
        usuario_robot = 'ROBOT_STOD'
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                sql = """
                DECLARE @MensajeTipo INT;
                DECLARE @MensajeDescripcion VARCHAR(200);
                
                EXEC CPRO_ObtenerDiasPagoCode 
                    @CODE = ?, 
                    @IDEMPRESA = ?, 
                    @Usuario = ?, 
                    @MensajeTipo = @MensajeTipo OUTPUT, 
                    @MensajeDescripcion = @MensajeDescripcion OUTPUT;
                """
                
                cursor.execute(sql, (codigo, id_empresa, usuario_robot))
                
                row = cursor.fetchone()
                
                if row:
                    # Columnas: Dias, STOD_Mensaje (Forma de pago), Moneda
                    dias = row.Dias
                    forma_pago = row.STOD_Mensaje
                    moneda = row.Moneda
                    return {
                        "exito": True,
                        "dias_credito": dias,
                        "forma_pago": forma_pago,
                        "moneda": moneda
                    }
                else:
                    return {"exito": False, "error": "No se encontraron condiciones para este Código."}
                    
        except Exception as e:
            log.error(f"Error en obtener_condiciones_por_codigo: {e}")
            return {"exito": False, "error": str(e)}
