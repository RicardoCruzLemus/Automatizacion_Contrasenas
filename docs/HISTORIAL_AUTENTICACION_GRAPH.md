# HISTORIAL DEL PROYECTO — Extractor de correos Outlook / Microsoft 365

Fecha: 2 de septiembre de 2026
Usuario: tmorales (tmorales@canella.com.gt), desarrollador. Tenant Microsoft 365 de Canella, S.A.
Contexto general: el usuario mantiene STOD, una aplicación ASP.NET Web Forms integrada con SAP Business One
sobre SQL Server. Este proyecto es independiente: un vaciado de correos para estadísticas y automatización.

Este documento resume la conversación completa con el asistente (Claude) para que otro asistente
(p. ej. Gemini) pueda continuar el trabajo con todo el contexto.

---

## 1. Requerimiento inicial

- Programa en Python que lea los correos del buzón empresarial de Outlook (Microsoft 365).
- Credenciales en un archivo `.env`.
- Salida: vaciado de datos manejable para estadísticas.
- Logs para depurar acciones y validar errores.
- Antecedente: existía una aplicación anterior (sin acceso al código) que fallaba con:
  `ERROR DE IMAP: Basic authentication is disabled. ... TI debe habilitar IMAP y deshabilitar MFA`.

## 2. Diagnóstico y decisión de arquitectura

- Ese mensaje de la app anterior es engañoso: Microsoft eliminó permanentemente la autenticación básica
  (usuario+contraseña por IMAP/POP/SMTP) en todos los tenants de Microsoft 365. TI no puede "habilitarla"
  y quitar MFA no ayuda. La única vía soportada es OAuth2.
- Se eligió **Microsoft Graph API** con **MSAL**, flujo **device code** (delegado): el usuario inicia sesión
  una vez en el navegador con MFA; el token se guarda en `.token_cache.json` y se renueva solo.
- Modo alternativo `AUTH_MODE=app` (client credentials, requiere secreto + consentimiento admin) para
  ejecución desatendida o para leer otros buzones vía `/users/{correo}`.
- Salida triple: CSV (UTF-8 con BOM para Excel), JSONL y SQLite acumulativa (`salida/correos.sqlite`,
  tabla `correos`, PK = id de Graph, `INSERT OR REPLACE`).
- Logs rotativos en `logs/extractor.log` (5 MB x 5), con formato `fecha | nivel | función | mensaje`.
  Los errores de Entra (`AADSTSxxxxx`) y HTTP (401/403/404/429) se registran con **causa probable**.
- Modo `--incremental`: guarda la última `receivedDateTime` por carpeta en `estado.json`.

## 3. Registro de la aplicación en Entra ID (realizado)

Pasos ejecutados por el usuario en https://entra.microsoft.com:
1. App registrations → New registration → nombre `Extractor Correos STOD`,
   "Solo inquilino único: Canella, S.A.", sin redirect URI.
2. Copiar Application (client) ID → `CLIENT_ID`, Directory (tenant) ID → `TENANT_ID`.
3. Authentication → Advanced settings → **Allow public client flows = Yes**.
4. API permissions → Microsoft Graph → Delegated → **Mail.Read** (además del `User.Read` que Entra agrega
   por defecto).
5. El botón "Grant admin consent" estaba deshabilitado (el usuario no es administrador). El administrador
   del tenant aprobó el consentimiento posteriormente.

## 4. Alternativa sin Entra: Outlook de escritorio (COM)

Ante la duda "¿y si no consigo el permiso del administrador?", se creó `extractor_outlook_com.py`:
- Usa `pywin32` (`win32com.client`) para leer el buzón desde el Outlook clásico ya abierto en Windows.
  Sin credenciales, sin MFA, sin permisos de admin.
- Misma salida (CSV/JSONL/SQLite con las mismas columnas) y mismo estilo de logs (`logs/extractor_com.log`).
- Limitaciones: solo Windows + Outlook clásico (el "nuevo Outlook" no expone COM); solo ve lo sincronizado
  en el .ost; más lento; para otro buzón se necesita que esté agregado al perfil de Outlook (`--buzon`).
- Conclusión discutida: COM sirve para arrancar; Graph es lo que escala a varios buzones
  (delegado con `Mail.Read.Shared`, o modo app con Application Access Policy).

## 5. Problema: se extrajo el buzón del administrador

- Causa: el administrador dio el consentimiento iniciando sesión con el device code **en la máquina del
  usuario**, su cuenta quedó en `.token_cache.json` y el script tomaba la primera cuenta del cache.
- Solución aplicada en el script:
  - Nueva variable `.env` `ACCOUNT_USERNAME`: solo se acepta esa cuenta del cache; si la sesión resulta
    de otro usuario, aborta con código 3.
  - Flag `--reauth`: borra el cache y obliga a iniciar sesión.
  - Log `SESIÓN INICIADA COMO: <upn>` (sale del id_token).
- Se recomendó borrar los archivos de salida generados con el buzón del administrador.

## 6. Preguntas sobre alcance y costo (respondidas)

- ¿Puedo ejecutar acciones en Python cuando llega X correo? Sí: capa de reglas sobre `asunto`/`de_correo`
  y ejecución programada de `--incremental` cada N minutos (polling). Webhooks de Graph son posibles pero
  requieren endpoint HTTPS público.
- Límite: con `Mail.Read` se puede leer y actuar fuera del correo; para marcar leído, mover, responder o
  reenviar se necesita `Mail.ReadWrite` / `Mail.Send`, lo que implica otra aprobación del administrador.
  Conviene pedir todos los permisos futuros en una sola solicitud.
- ¿Vaciado del día + filtro por asunto + reportería? Sí, es el uso previsto (`--dias 1` o `--incremental`,
  luego SQL sobre `correos.sqlite` o pandas).
- ¿Costo? Ninguno: Graph, el App Registration y las llamadas de lectura de correo están incluidos en la
  licencia M365. No hay suscripción Azure ni cobro por volumen; solo throttling (que el script maneja).

## 7. Descarga de adjuntos a un servidor de archivos

- Es posible con `Mail.Read` (no requiere permiso nuevo). Se agregó `--adjuntos` a `extractor_outlook.py`:
  - Destino `ATTACHMENTS_DIR` (local o UNC `\\servidor\compartido`), escrito con la identidad Windows del
    usuario que ejecuta; si no hay permiso falla al inicio.
  - Estructura `DESTINO/AAAA-MM/AAAAMMDD_HHMM_asunto/archivo.ext`.
  - Descarga en streaming vía `/attachments/{id}/$value`, escribe `.part` y renombra al terminar.
  - Tabla `adjuntos` en la misma SQLite (id, correo_id, nombre, tipo, tamaño, ruta, sha256, fecha, asunto,
    remitente). No re-descarga lo ya registrado.
  - Filtros: `--ext pdf,xlsx,xml` / `ATTACHMENTS_EXT`, `--inline` para imágenes incrustadas,
    `ATTACHMENTS_MAX_MB`. Omite `referenceAttachment` (enlaces OneDrive/SharePoint) e `itemAttachment`
    (correos/citas adjuntas).
- SFTP sería el mismo flujo con `paramiko`; SharePoint requeriría `Files.ReadWrite`.

## 8. Errores encontrados en pruebas reales y correcciones

| Síntoma en el log | Causa | Corrección |
|---|---|---|
| `ext: '# pdf,xlsx,xml (vacío = todas)'`, 4 adjuntos omitidos | python-dotenv no descarta comentarios en línea; el valor llegaba empezando con `#` | `cfg()` limpia comentarios en línea y valores que empiezan con `#`; `.env.example` sin comentarios al lado de los valores |
| `ValueError: invalid literal for int()` al abortar | `SystemExit("texto")` pasaba por `int(e.code)` | El manejador distingue código string (log + return 2) |
| `HTTP 403 Authorization_RequestDenied` en `/me` | Verificación de perfil que requería `User.Read` en el token | Se eliminó la llamada a `/me`; la identidad se toma del id_token |
| Pantalla "Se necesita la aprobación del administrador" | Se había agregado `User.Read` a los scopes solicitados → nuevo consentimiento | Scopes vuelven a `["Mail.Read"]` únicamente |
| `sqlite3.OperationalError: database is locked` | Dos conexiones SQLite (correos y adjuntos) sobre el mismo archivo con transacción abierta | `GestorAdjuntos` reutiliza la conexión de `Escritor`; `timeout=30`; cierre en orden |
| `FileNotFoundError ... HDR10+_ \Televisor...` | Nombre de carpeta terminaba en espacio; Windows lo recorta al crear | `_nombre_seguro()` recorta espacios/puntos finales tras truncar, elimina invisibles (nbsp, zero-width), evita nombres reservados (CON, NUL, COM1...) |

Estado al cierre: autenticación funcionando con la cuenta correcta (`SESIÓN INICIADA COMO: tmorales@...`),
29 correos de 7 días extraídos correctamente. Pendiente de confirmar la corrida de adjuntos tras la última
corrección (se recomendó borrar `salida/correos.sqlite` y la carpeta `ARCHIVOS_CORREOS/2026-08` incompleta).

## 9. Archivos del proyecto

- `extractor_outlook.py` — extractor principal (Graph API + MSAL). Flags: `--carpeta`, `--dias`,
  `--incremental`, `--incluir-cuerpo`, `--limite`, `--solo-carpetas`, `--adjuntos`, `--adjuntos-dir`,
  `--ext`, `--inline`, `--reauth`.
- `extractor_outlook_com.py` — alternativa vía Outlook de escritorio (Windows, pywin32).
- `.env.example` — plantilla de configuración (TENANT_ID, CLIENT_ID, AUTH_MODE, ACCOUNT_USERNAME,
  CLIENT_SECRET, MAILBOX, MAIL_FOLDER, DAYS_BACK, OUTPUT_DIR, LOG_DIR, LOG_LEVEL, TOKEN_CACHE_FILE,
  ATTACHMENTS_DIR, ATTACHMENTS_EXT, ATTACHMENTS_MAX_MB).
- `requirements.txt` — msal, requests, python-dotenv, pywin32 (solo Windows).
- `README.md` — guía de registro en Entra, uso, salidas, depuración, alternativa COM y adjuntos.
- `.gitignore` — excluye `.env`, cache de tokens, estado, logs y salida.

## 10. Ideas pendientes / siguientes pasos sugeridos

- Capa de reglas (asunto/remitente → acción: stored procedure, aviso Teams, etc.) + tarea programada con
  `--incremental --adjuntos`.
- Parámetro `--asunto` para filtrar en el servidor con `$filter`/`$search` de Graph.
- Decidir si se pedirán `Mail.ReadWrite` / `Mail.Send` (una sola solicitud al administrador).
- Variante SFTP para el destino de adjuntos si el servidor es Linux.
- Reportería sobre `correos.sqlite` (ej.: correos por remitente, con adjuntos, por día).
