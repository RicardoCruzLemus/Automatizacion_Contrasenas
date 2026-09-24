# Automatización de Contraseñas (STOD Auto) 🤖📄

Este proyecto es un sistema de automatización empresarial para el grupo Canella. Se encarga de monitorear un buzón de correo electrónico de Microsoft Exchange, procesar los documentos adjuntos (Facturas y Órdenes de Compra) mediante Inteligencia Artificial (OCR), y generar automáticamente las **Contraseñas de Pago** para los proveedores.

## 🚀 Características Principales

1. **Lectura de Correos (Graph API)**: Se conecta silenciosamente al correo oficial (`rcruz@canella.com.gt`) vía Microsoft Graph API para leer mensajes no leídos.
2. **OCR Inteligente**: Extrae de forma inteligente información vital de los PDF (NIT, Nombre, Total, Referencias de Factura, Número de OC) utilizando `EasyOCR` y conversiones de PDF a imagen.
3. **Validación de Negocio (STOD SQL Server)**: Consulta la base de datos de producción (STOD en `.70`) para validar que el proveedor exista y obtener sus días de crédito y forma de pago exactos.
4. **Cálculo de Fechas de Pago**: Calcula automáticamente la fecha del próximo viernes según los días de crédito del proveedor.
5. **Generación de Contraseñas PDF**: Construye al vuelo un documento PDF profesional ("Comprobante_STOD.pdf") con el listado de facturas aceptadas.
6. **Clasificación y Anti-Duplicados**: Almacena los archivos en una ruta de red compartida clasificados por: `Empresa / Año / Dia-Mes / NIT / Autorizador / OC`. Si detecta documentos incompletos los envía a `Parciales`, y si detecta reenvíos de la misma factura, los bloquea enviándolos a `Rechazadas`.
7. **Dashboard Web (Flask)**: Ofrece un panel de control en el navegador para que los usuarios puedan visualizar fácilmente qué trámites fueron Aceptados, cuáles están Parciales y cuáles fueron Rechazados.

---

## 🛠️ Tecnologías Utilizadas

- **Lenguaje:** Python 3.12
- **Web Framework:** Flask (para el Dashboard)
- **Base de Datos Local:** SQLite (`app.db` para rastrear los correos leídos)
- **Base de Datos Externa:** SQL Server (Vía `pyodbc` para consultar el STOD)
- **Lectura OCR:** `EasyOCR` + `pdf2image` + `Poppler`
- **Generación de PDFs:** `fpdf2`
- **Conexión de Correo:** Microsoft Graph API (`msal`, `requests`)

---

## 📂 Estructura del Proyecto

```text
AUTOMATIZACION_CONTRASEÑAS/
│
├── app/
│   ├── routes.py                 # Rutas del Dashboard Web (Flask)
│   ├── models.py                 # Esquema de la BD local (EmailLog)
│   ├── templates/                # Archivos HTML (index.html)
│   ├── static/                   # CSS, JS, e imágenes (logo)
│   └── services/
│       ├── graph_auth.py         # Autenticación con Microsoft Graph API
│       ├── email_service.py      # Lógica central: procesar correos, mover archivos, crear PDFs
│       ├── ocr_service.py        # Extracción de texto con EasyOCR y Expresiones Regulares
│       ├── stod_db_service.py    # Conexión de SOLO LECTURA a la BD SQL Server .70
│       └── pdf_generator.py      # Diseño y creación de los comprobantes PDF
│
├── run.py                        # Punto de entrada principal (Inicia web y proceso de fondo)
├── config.py                     # Carga de variables de entorno (env_config)
├── requirements.txt              # Dependencias del proyecto
└── .env                          # Variables de entorno secretas (Claves, rutas, contraseñas)
```

---

## ⚙️ Configuración (.env)

El proyecto requiere un archivo `.env` en la raíz con la siguiente estructura:

```env
# Configuración Graph API
TENANT_ID="tu-tenant-id"
CLIENT_ID="tu-client-id"
CLIENT_SECRET="tu-secret"
EMAIL_ACCOUNT="rcruz@canella.com.gt"
EMAIL_SUBJECT_FILTER="tramite de contrseña,tramite contraseña"

# Rutas de Red
STORAGE_FOLDER="\\128.1.200.70\AUTOMATIZACION_CONTRASEÑAS"

# STOD Base de Datos (.70)
STOD_DB_SERVER="128.1.200.70"
STOD_DB_NAME="STOD"
STOD_DB_USER="sa"
STOD_DB_PASS="***********"

# Dashboard Web
FLASK_SECRET_KEY="una-clave-secreta-cualquiera"
```

---

## 🏃‍♂️ Cómo Ejecutarlo

1. **Activar el Entorno Virtual** (si aplica)
   ```cmd
   venv\Scripts\activate
   ```
2. **Instalar Dependencias** (si es la primera vez)
   ```cmd
   pip install -r requirements.txt
   ```
3. **Iniciar la Aplicación**
   ```cmd
   python run.py
   ```
4. **Ver el Dashboard**
   Abre tu navegador web y entra a: `http://127.0.0.1:5000`

> **Nota de Producción:** El programa se quedará en ejecución en la consola. Cada 60 segundos revisará el correo en busca de nuevos trámites de contraseñas.

---

## ⚠️ Reglas de Negocio Importantes

- **Seguridad en BD Externa:** La conexión a la base de datos `128.1.200.70` es **estrictamente de solo lectura**. El robot nunca hace `INSERT`, `UPDATE` o `DELETE` en el STOD.
- **Tolerancia a Fallos de Red:** Si se pierde la conexión de red con el `.70` mientras procesa un correo, el programa no marcará el correo como "Leído", asegurando que lo intente nuevamente al regresar la conexión.
- **Renombramiento Inteligente:** El robot previene el límite de longitud de archivos en Windows (MAX_PATH) aplicando un hash a las carpetas temporales, y renombra inteligentemente los PDFs finales con la nomenclatura: `OC-XXXXXXXX.pdf` y `FAC-XXXXXXXX.pdf`.
