# Extractor de correos Outlook / Microsoft 365

Vaciado de correos a **CSV + JSONL + SQLite** usando Microsoft Graph API con OAuth2.
Reemplaza el enfoque IMAP con usuario/contraseña, que Microsoft eliminó de forma permanente
(el error `Basic authentication is disabled` **no** se resuelve habilitando IMAP ni quitando MFA).

## 1. Registrar la aplicación en Entra ID (una sola vez)

1. Entra a <https://entra.microsoft.com> → **Identity → Applications → App registrations → New registration**.
2. Nombre: `Extractor Correos STOD` (o el que prefieras). *Supported account types*: **Single tenant**. Sin redirect URI. → **Register**.
3. Copia **Application (client) ID** → `CLIENT_ID` y **Directory (tenant) ID** → `TENANT_ID`.
4. **Authentication** → *Advanced settings* → **Allow public client flows = Yes** → Save.
5. **API permissions** → Add a permission → Microsoft Graph → **Delegated** → `Mail.Read` → Add.
   - Si aparece el botón *Grant admin consent*, púlsalo. Si no, la primera vez que inicies sesión
     se te pedirá consentimiento (o tu tenant requerirá que un admin lo apruebe).

Si tu empresa no permite que los usuarios registren aplicaciones, envía esto a TI:

> Necesito un App Registration en Entra ID (single tenant) con permiso **delegado** Microsoft Graph
> `Mail.Read`, con *Allow public client flows* habilitado y consentimiento de administrador otorgado.
> Solo requiero el Client ID y el Tenant ID. La app lee únicamente mi propio buzón con mi sesión.

### Alternativa: modo aplicación (sin sesión interactiva)
Para correr desatendido (tarea programada) o leer otros buzones: permiso de **Application** `Mail.Read`,
consentimiento de admin, un **Client secret**, y en el `.env`: `AUTH_MODE=app`, `CLIENT_SECRET=...`,
`MAILBOX=correo@empresa.com`. TI probablemente quiera restringirlo con una *Application Access Policy*
(`New-ApplicationAccessPolicy`) para que solo alcance tu buzón.

## 2. Instalación

```bash
pip install -r requirements.txt
cp .env.example .env      # y completa TENANT_ID / CLIENT_ID
```

## 3. Uso

```bash
python extractor_outlook.py --solo-carpetas          # ver carpetas disponibles
python extractor_outlook.py                          # últimos 30 días de inbox
python extractor_outlook.py --dias 0 --carpeta all   # todo el historial, todas las carpetas
python extractor_outlook.py --carpeta sentitems --dias 365
python extractor_outlook.py --incremental            # solo lo nuevo desde la última corrida
python extractor_outlook.py --incluir-cuerpo --limite 50   # prueba con cuerpo de texto
```

La primera ejecución muestra un código y una URL (`https://microsoft.com/devicelogin`): entras con
tu cuenta empresarial (MFA incluido) y listo. El token queda en `.token_cache.json` y se renueva solo.

## 4. Salidas

| Archivo | Contenido |
|---|---|
| `salida/correos_FECHA.csv` | Una fila por correo (UTF-8 con BOM, abre bien en Excel) |
| `salida/correos_FECHA.jsonl` | Lo mismo en JSON por línea |
| `salida/correos.sqlite` | Tabla `correos` acumulativa (clave `id`, sin duplicados) |
| `estado.json` | Última fecha extraída por carpeta, para `--incremental` |
| `logs/extractor.log` | Log rotativo (5 MB × 5) de toda la actividad |

Ejemplo de consulta para estadísticas:

```sql
SELECT de_correo, COUNT(*) total, SUM(tiene_adjuntos='True') con_adjuntos
FROM correos
WHERE fecha_recibido >= '2026-01-01'
GROUP BY de_correo ORDER BY total DESC;
```

## 5. Depuración

- `LOG_LEVEL=DEBUG` en el `.env` registra cada request a Graph y los parámetros usados.
- Los errores de autenticación (`AADSTSxxxxx`) y HTTP (401/403/404/429) se registran con la
  **causa probable** y la acción correctiva.
- Códigos de salida: `0` OK · `1` error no controlado · `2` fallo de autenticación · `3` sesión de otra cuenta · `130` interrumpido.
- **Extrae el buzón de otra persona (p. ej. del administrador):** su cuenta quedó en `.token_cache.json`.
  Define `ACCOUNT_USERNAME=tu.correo@empresa.com` en el `.env` y ejecuta con `--reauth`; el log muestra
  `SESIÓN INICIADA COMO` para confirmar.

## 6. Alternativa sin registro en Entra: `extractor_outlook_com.py`

Si no puedes obtener el consentimiento del administrador, `extractor_outlook_com.py` lee el buzón
directamente desde **Outlook de escritorio** (Windows, Outlook clásico) usando la sesión ya abierta.
No pide credenciales ni MFA. Misma salida (CSV/JSONL/SQLite) y mismos logs (`logs/extractor_com.log`).

```bash
pip install pywin32
python extractor_outlook_com.py --solo-carpetas
python extractor_outlook_com.py --carpeta "Bandeja de entrada" --dias 365
python extractor_outlook_com.py --carpeta all --dias 0
```

Limitaciones: solo funciona con Outlook abierto o instalado en la misma máquina; el "nuevo Outlook"
no expone COM; la primera vez Windows puede mostrar un aviso de seguridad de Outlook pidiendo permitir
el acceso programático (acepta por 10 minutos o pide a TI que agregue la excepción). Solo verás los
correos que Outlook tenga descargados en el .ost (revisa en Configuración de cuenta el "correo para
mantener sin conexión": ponlo en *Todo* si quieres historial completo).

## 7. Adjuntos a un servidor de archivos

```bash
python extractor_outlook.py --dias 7 --adjuntos                       # todos los archivos
python extractor_outlook.py --dias 7 --adjuntos --ext pdf,xlsx,xml    # solo esos tipos
python extractor_outlook.py --incremental --adjuntos                  # lo nuevo, para tarea programada
```

- El destino se define en `ATTACHMENTS_DIR` (o `--adjuntos-dir`): puede ser una carpeta local o una
  ruta UNC `\\servidor\compartido\carpeta`. Se escribe con las credenciales de red del usuario que
  ejecuta el script; si no tiene permiso el script falla al inicio, no a mitad de la descarga.
- Estructura: `DESTINO/AAAA-MM/AAAAMMDD_HHMM_asunto/archivo.ext`.
- Cada archivo queda en la tabla `adjuntos` de `correos.sqlite` (ruta, tamaño, SHA-256, correo origen),
  así que no se vuelve a descargar lo que ya existe y puedes cruzarlo con la tabla `correos` por `correo_id`.
- Se omiten por defecto las imágenes incrustadas de firmas (`--inline` para incluirlas), los enlaces a
  OneDrive/SharePoint (no son archivos) y los correos adjuntos como .msg.
- Para SFTP/Linux el flujo es el mismo cambiando la escritura por `paramiko`; para SharePoint se
  necesitaría el permiso `Files.ReadWrite` adicional.
