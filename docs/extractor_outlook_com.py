#!/usr/bin/env python3
"""
Extractor de correos desde Outlook de escritorio (Windows) vía COM.

Alternativa al extractor por Graph API cuando no se puede registrar la app en Entra ID.
Usa la sesión que Outlook ya tiene abierta: no requiere credenciales, MFA ni permisos de admin.

Requisitos: Windows + Outlook clásico (no "nuevo Outlook") + pip install pywin32 python-dotenv

Uso:
    python extractor_outlook_com.py                       # Bandeja de entrada, últimos 30 días
    python extractor_outlook_com.py --carpeta "Elementos enviados" --dias 365
    python extractor_outlook_com.py --carpeta all --dias 0 # todo el buzón
    python extractor_outlook_com.py --incremental
    python extractor_outlook_com.py --solo-carpetas
"""
import argparse
import csv
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

try:
    import pythoncom
    import win32com.client
except ImportError:
    sys.exit("Falta pywin32. Instala con: pip install pywin32")

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

OL_MAIL_ITEM = 43          # olMail
OL_FOLDER_INBOX = 6
OL_FOLDER_SENT = 5
OL_FOLDER_DRAFTS = 16
OL_FOLDER_DELETED = 3
OL_FOLDER_JUNK = 23

CARPETAS_CONOCIDAS = {
    "inbox": OL_FOLDER_INBOX, "sentitems": OL_FOLDER_SENT, "drafts": OL_FOLDER_DRAFTS,
    "deleteditems": OL_FOLDER_DELETED, "junkemail": OL_FOLDER_JUNK,
}

COLUMNAS_SALIDA = [
    "id", "internet_message_id", "conversation_id", "fecha_recibido", "fecha_enviado",
    "asunto", "de_nombre", "de_correo", "para", "cc", "cco", "leido", "borrador",
    "tiene_adjuntos", "importancia", "categorias", "marcado", "vista_previa",
    "web_link", "carpeta_id", "carpeta",
]

# Propiedad MAPI para obtener el SMTP real cuando el remitente es interno (tipo EX)
PR_SMTP_ADDRESS = "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"
PR_INTERNET_MESSAGE_ID = "http://schemas.microsoft.com/mapi/proptag/0x1035001E"


def cfg(nombre, defecto=None):
    return os.getenv(nombre, defecto)


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
def configurar_logging(nivel: str, dir_logs: Path) -> logging.Logger:
    dir_logs.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("extractor_com")
    logger.setLevel(getattr(logging, nivel.upper(), logging.INFO))
    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(funcName)s | %(message)s")
    fh = RotatingFileHandler(dir_logs / "extractor_com.log", maxBytes=5_000_000,
                             backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


log = logging.getLogger("extractor_com")


# --------------------------------------------------------------------------- #
# Conexión a Outlook
# --------------------------------------------------------------------------- #
def conectar_outlook():
    pythoncom.CoInitialize()
    try:
        app = win32com.client.Dispatch("Outlook.Application")
        ns = app.GetNamespace("MAPI")
        # Si Outlook estaba cerrado, esto lo abre en segundo plano y carga el perfil por defecto
        ns.Logon("", "", False, False)
        cuenta = None
        try:
            cuenta = ns.Accounts.Item(1).SmtpAddress
        except Exception:
            pass
        log.info("Conectado a Outlook (%s). Cuenta principal: %s", app.Version, cuenta)
        return ns
    except Exception as e:
        log.error("No se pudo conectar a Outlook: %s", e)
        log.error("CAUSA PROBABLE: Outlook clásico no está instalado, o está activo el 'nuevo Outlook' "
                  "(que no expone COM), o hay un diálogo abierto en Outlook bloqueando la automatización.")
        raise SystemExit(2)


def recorrer_carpetas(carpeta, prefijo=""):
    """Generador recursivo (ruta_legible, objeto_folder)."""
    nombre = f"{prefijo}/{carpeta.Name}" if prefijo else carpeta.Name
    yield nombre, carpeta
    try:
        for sub in carpeta.Folders:
            yield from recorrer_carpetas(sub, nombre)
    except Exception as e:
        log.debug("No se pudo recorrer subcarpetas de %s: %s", nombre, e)


def resolver_carpeta(ns, nombre: str, buzon: str | None):
    """Acepta: inbox/sentitems/..., 'all', o una ruta como 'Bandeja de entrada/Proveedores'."""
    raiz = ns.Folders.Item(buzon) if buzon else ns.GetDefaultFolder(OL_FOLDER_INBOX).Parent
    if nombre.lower() == "all":
        return [(r, f) for r, f in recorrer_carpetas(raiz)]
    if nombre.lower() in CARPETAS_CONOCIDAS:
        f = ns.GetDefaultFolder(CARPETAS_CONOCIDAS[nombre.lower()])
        return [(f.Name, f)]
    # Ruta por nombres visibles
    actual = raiz
    for parte in nombre.split("/"):
        try:
            actual = actual.Folders.Item(parte)
        except Exception:
            log.error("Carpeta '%s' no encontrada. Usa --solo-carpetas para ver los nombres exactos.", nombre)
            raise SystemExit(2)
    return [(nombre, actual)]


# --------------------------------------------------------------------------- #
# Transformación
# --------------------------------------------------------------------------- #
def smtp_de(item) -> str:
    """Devuelve el SMTP del remitente aunque sea una dirección Exchange interna (/o=.../cn=...)."""
    try:
        if item.SenderEmailType == "EX":
            return item.Sender.GetExchangeUser().PrimarySmtpAddress
        return item.SenderEmailAddress or ""
    except Exception:
        try:
            return item.PropertyAccessor.GetProperty(PR_SMTP_ADDRESS) or ""
        except Exception:
            return item.SenderEmailAddress or ""


def destinatarios(item, tipo: int) -> str:
    """tipo: 1=Para, 2=CC, 3=CCO"""
    partes = []
    try:
        for r in item.Recipients:
            if r.Type != tipo:
                continue
            correo = ""
            try:
                correo = r.PropertyAccessor.GetProperty(PR_SMTP_ADDRESS)
            except Exception:
                correo = r.Address or ""
            partes.append(f"{r.Name} <{correo}>")
    except Exception:
        pass
    return "; ".join(partes)


def fecha_iso(valor) -> str | None:
    if not valor:
        return None
    try:
        # pywintypes.datetime → datetime con tz local
        dt = datetime(valor.year, valor.month, valor.day, valor.hour, valor.minute, valor.second)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return str(valor)


def aplanar(item, carpeta_ruta: str, incluir_cuerpo: bool) -> dict:
    de_nombre = getattr(item, "SenderName", None)
    try:
        internet_id = item.PropertyAccessor.GetProperty(PR_INTERNET_MESSAGE_ID)
    except Exception:
        internet_id = None
    importancia = {0: "low", 1: "normal", 2: "high"}.get(getattr(item, "Importance", 1), "normal")
    marcado = {0: "notFlagged", 1: "complete", 2: "flagged"}.get(getattr(item, "FlagStatus", 0))
    fila = {
        "id": item.EntryID,
        "internet_message_id": internet_id,
        "conversation_id": getattr(item, "ConversationID", None),
        "fecha_recibido": fecha_iso(getattr(item, "ReceivedTime", None)),
        "fecha_enviado": fecha_iso(getattr(item, "SentOn", None)),
        "asunto": item.Subject,
        "de_nombre": de_nombre,
        "de_correo": smtp_de(item),
        "para": destinatarios(item, 1),
        "cc": destinatarios(item, 2),
        "cco": destinatarios(item, 3),
        "leido": not item.UnRead,
        "borrador": not bool(getattr(item, "Sent", True)),
        "tiene_adjuntos": item.Attachments.Count > 0,
        "importancia": importancia,
        "categorias": item.Categories or "",
        "marcado": marcado,
        "vista_previa": (item.Body or "")[:255].replace("\r\n", " ").strip(),
        "web_link": None,
        "carpeta_id": item.Parent.EntryID,
        "carpeta": carpeta_ruta,
    }
    if incluir_cuerpo:
        fila["cuerpo"] = item.Body
    return fila


# --------------------------------------------------------------------------- #
# Salida (idéntica al extractor Graph para poder mezclar datos)
# --------------------------------------------------------------------------- #
class Escritor:
    def __init__(self, dir_salida: Path, incluir_cuerpo: bool):
        dir_salida.mkdir(parents=True, exist_ok=True)
        marca = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.columnas = COLUMNAS_SALIDA + (["cuerpo"] if incluir_cuerpo else [])
        self.ruta_csv = dir_salida / f"correos_{marca}.csv"
        self.ruta_jsonl = dir_salida / f"correos_{marca}.jsonl"
        self.ruta_db = dir_salida / "correos.sqlite"
        self._csv_f = open(self.ruta_csv, "w", newline="", encoding="utf-8-sig")
        self._csv = csv.DictWriter(self._csv_f, fieldnames=self.columnas, extrasaction="ignore")
        self._csv.writeheader()
        self._jsonl = open(self.ruta_jsonl, "w", encoding="utf-8")
        self._db = sqlite3.connect(self.ruta_db)
        cols_sql = ", ".join(f'"{c}" TEXT' for c in self.columnas if c != "id")
        self._db.execute(f'CREATE TABLE IF NOT EXISTS correos ("id" TEXT PRIMARY KEY, {cols_sql}, "extraido_en" TEXT)')
        existentes = {r[1] for r in self._db.execute("PRAGMA table_info(correos)")}
        for c in self.columnas:
            if c not in existentes:
                self._db.execute(f'ALTER TABLE correos ADD COLUMN "{c}" TEXT')
        self._db.execute("CREATE INDEX IF NOT EXISTS ix_fecha ON correos(fecha_recibido)")
        self._db.execute("CREATE INDEX IF NOT EXISTS ix_de ON correos(de_correo)")
        self.n = 0
        self.ultima_fecha = None

    def escribir(self, fila: dict):
        self._csv.writerow(fila)
        self._jsonl.write(json.dumps(fila, ensure_ascii=False, default=str) + "\n")
        cols = self.columnas + ["extraido_en"]
        valores = [str(fila.get(c)) if fila.get(c) is not None else None for c in self.columnas]
        valores.append(datetime.now(timezone.utc).isoformat())
        self._db.execute(
            f"INSERT OR REPLACE INTO correos ({', '.join(f'\"{c}\"' for c in cols)}) "
            f"VALUES ({', '.join('?' * len(cols))})", valores)
        self.n += 1
        if fila.get("fecha_recibido") and (not self.ultima_fecha or fila["fecha_recibido"] > self.ultima_fecha):
            self.ultima_fecha = fila["fecha_recibido"]
        if self.n % 500 == 0:
            self._db.commit()
            log.info("Guardados %d correos...", self.n)

    def cerrar(self):
        self._csv_f.close()
        self._jsonl.close()
        self._db.commit()
        total = self._db.execute("SELECT COUNT(*) FROM correos").fetchone()[0]
        self._db.close()
        log.info("Salida: %s | %s | %s (total en BD: %d)", self.ruta_csv.name, self.ruta_jsonl.name,
                 self.ruta_db.name, total)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    p = argparse.ArgumentParser(description="Vaciado de correos desde Outlook de escritorio (COM)")
    p.add_argument("--carpeta", default=cfg("MAIL_FOLDER", "inbox"),
                   help="inbox, sentitems, drafts, deleteditems, junkemail, all, o ruta 'Bandeja de entrada/Sub'")
    p.add_argument("--dias", type=int, default=int(cfg("DAYS_BACK", "30")), help="0 = sin límite")
    p.add_argument("--incremental", action="store_true")
    p.add_argument("--incluir-cuerpo", action="store_true")
    p.add_argument("--limite", type=int, default=None)
    p.add_argument("--solo-carpetas", action="store_true")
    p.add_argument("--buzon", default=cfg("MAILBOX_DISPLAY_NAME"),
                   help="Nombre del buzón tal como aparece en Outlook (si tienes varios)")
    args = p.parse_args()

    configurar_logging(cfg("LOG_LEVEL", "INFO"), BASE_DIR / cfg("LOG_DIR", "logs"))
    log.info("=" * 60)
    log.info("Inicio | args=%s", vars(args))
    inicio = time.time()

    try:
        ns = conectar_outlook()

        if args.solo_carpetas:
            raiz = ns.Folders.Item(args.buzon) if args.buzon else ns.GetDefaultFolder(OL_FOLDER_INBOX).Parent
            for ruta, f in recorrer_carpetas(raiz):
                try:
                    print(f"{ruta:60s} {f.Items.Count:>6} items")
                except Exception:
                    print(f"{ruta:60s}      ?")
            return 0

        ruta_estado = BASE_DIR / "estado_com.json"
        estado = json.loads(ruta_estado.read_text(encoding="utf-8")) if ruta_estado.exists() else {}
        clave = f"{args.buzon or 'default'}::{args.carpeta}"

        desde = None
        if args.incremental and estado.get(clave):
            desde = datetime.fromisoformat(estado[clave].replace("Z", "+00:00")).astimezone()
            log.info("Modo incremental desde %s", desde)
        elif args.dias > 0:
            desde = (datetime.now(timezone.utc) - timedelta(days=args.dias)).astimezone()
            log.info("Rango: últimos %d días", args.dias)
        else:
            log.info("Sin límite de fecha")

        escritor = Escritor(BASE_DIR / cfg("OUTPUT_DIR", "salida"), args.incluir_cuerpo)
        errores = 0
        try:
            for ruta, carpeta in resolver_carpeta(ns, args.carpeta, args.buzon):
                if carpeta.DefaultItemType != 0:   # 0 = olMailItem; salta calendario, contactos, etc.
                    log.debug("Omitida carpeta no de correo: %s", ruta)
                    continue
                items = carpeta.Items
                items.Sort("[ReceivedTime]", True)
                if desde:
                    # Restrict usa formato de fecha local de Outlook; el formato de 24h suele funcionar
                    filtro = f"[ReceivedTime] >= '{desde.strftime('%m/%d/%Y %H:%M')}'"
                    try:
                        items = items.Restrict(filtro)
                    except Exception as e:
                        log.warning("Restrict falló (%s); se filtrará en Python", e)
                log.info("Carpeta '%s': %d elementos a revisar", ruta, items.Count)

                n_carp = 0
                item = items.GetFirst()
                while item is not None:
                    try:
                        if item.Class == OL_MAIL_ITEM:
                            if desde and item.ReceivedTime and \
                               datetime(item.ReceivedTime.year, item.ReceivedTime.month, item.ReceivedTime.day,
                                        item.ReceivedTime.hour, item.ReceivedTime.minute).astimezone() < desde:
                                item = items.GetNext()
                                continue
                            escritor.escribir(aplanar(item, ruta, args.incluir_cuerpo))
                            n_carp += 1
                            if args.limite and escritor.n >= args.limite:
                                raise StopIteration
                    except StopIteration:
                        raise
                    except Exception:
                        errores += 1
                        log.exception("Error procesando un elemento en %s", ruta)
                    item = items.GetNext()
                log.info("Carpeta '%s': %d correos extraídos", ruta, n_carp)
        except StopIteration:
            log.info("Límite de %d alcanzado", args.limite)
        finally:
            escritor.cerrar()

        if escritor.ultima_fecha:
            estado[clave] = escritor.ultima_fecha
            ruta_estado.write_text(json.dumps(estado, indent=2), encoding="utf-8")

        log.info("FIN OK | correos=%d | errores=%d | %.1fs", escritor.n, errores, time.time() - inicio)
        return 0

    except SystemExit as e:
        return int(e.code or 0)
    except KeyboardInterrupt:
        log.warning("Interrumpido por el usuario")
        return 130
    except Exception:
        log.exception("ERROR NO CONTROLADO")
        return 1
    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    sys.exit(main())
