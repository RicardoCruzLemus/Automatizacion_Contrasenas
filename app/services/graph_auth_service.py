"""
Servicio de autenticación con Microsoft Graph API usando MSAL.
Soporta dos modos:
  - delegated: El usuario inicia sesión con Device Code (soporta MFA). Lee su propia bandeja.
  - app: Client Credentials con CLIENT_SECRET. Lee cualquier buzón (requiere admin consent).
"""
import json
import logging
import os
from pathlib import Path

import msal
import requests
from dotenv import load_dotenv

# Cargamos el .env desde la raíz del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

log = logging.getLogger(__name__)

GRAPH_URL = "https://graph.microsoft.com/v1.0"
SCOPES_DELEGADOS = ["Mail.Read"]
SCOPES_APP = ["https://graph.microsoft.com/.default"]


class GraphAuthService:
    """
    Maneja la autenticación con Microsoft Graph API via MSAL.
    - Modo 'delegated': Device Code Flow (compatible con MFA). 
    - Modo 'app': Client Credentials Flow (sin intervención del usuario).
    El token se guarda en disco (cache) para no volver a pedir login en cada reinicio.
    """
    
    def __init__(self):
        self.tenant_id = os.getenv("TENANT_ID", "")
        self.client_id = os.getenv("CLIENT_ID", "")
        self.client_secret = os.getenv("CLIENT_SECRET", "")
        self.modo = os.getenv("AUTH_MODE", "delegated").lower()
        self.usuario_esperado = (os.getenv("ACCOUNT_USERNAME") or "").strip().lower() or None
        self.mailbox = os.getenv("MAILBOX", "")
        self.token_cache_file = BASE_DIR / os.getenv("TOKEN_CACHE_FILE", ".token_cache.json")
        
        if not self.tenant_id or not self.client_id:
            raise ValueError(
                "Faltan TENANT_ID y/o CLIENT_ID en el archivo .env. "
                "Configúralos con los valores de la App Registration de Azure."
            )
        
        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        self.cache = msal.SerializableTokenCache()
        
        # Cargar cache de token existente para evitar re-login
        if self.token_cache_file.exists():
            self.cache.deserialize(self.token_cache_file.read_text(encoding="utf-8"))
            log.debug("Cache de token cargado desde %s", self.token_cache_file)
        
        # Inicializar la aplicación MSAL
        if self.modo == "app":
            if not self.client_secret:
                raise ValueError("AUTH_MODE=app requiere CLIENT_SECRET en el .env")
            self.app = msal.ConfidentialClientApplication(
                self.client_id,
                authority=self.authority,
                client_credential=self.client_secret,
                token_cache=self.cache
            )
        else:
            self.app = msal.PublicClientApplication(
                self.client_id,
                authority=self.authority,
                token_cache=self.cache
            )
    
    def _guardar_cache(self):
        """Persiste el token en disco si cambió."""
        if self.cache.has_state_changed:
            self.token_cache_file.write_text(self.cache.serialize(), encoding="utf-8")
            try:
                os.chmod(self.token_cache_file, 0o600)
            except OSError:
                pass
            log.debug("Cache de token guardado en disco.")
    
    def _flujo_device_code(self) -> dict:
        """Inicia el flujo de Device Code: el usuario abre un navegador y mete un código."""
        flujo = self.app.initiate_device_flow(scopes=SCOPES_DELEGADOS)
        if "user_code" not in flujo:
            raise RuntimeError(f"No se pudo iniciar Device Code Flow: {json.dumps(flujo, indent=2)}")
        
        log.info("Se requiere inicio de sesión interactivo (solo la primera vez; luego usa el cache).")
        print("\n" + "=" * 70)
        print(flujo["message"])  # Mensaje: "Abre https://microsoft.com/devicelogin y escribe el código XXXXXXXX"
        if self.usuario_esperado:
            print(f">>> INICIA SESIÓN CON: {self.usuario_esperado} <<<")
        print("=" * 70 + "\n")
        return self.app.acquire_token_by_device_flow(flujo)
    
    def obtener_token(self) -> str:
        """Obtiene un access token válido. Usa el cache si existe, si no, pide login."""
        resultado = None
        
        if self.modo == "app":
            resultado = self.app.acquire_token_for_client(scopes=SCOPES_APP)
        else:
            cuentas = self.app.get_accounts()
            cuenta = None
            if cuentas:
                log.info("Cuentas en cache: %s", [c.get("username") for c in cuentas])
                if self.usuario_esperado:
                    for c in cuentas:
                        if (c.get("username") or "").lower() == self.usuario_esperado:
                            cuenta = c
                            break
                else:
                    cuenta = cuentas[0]
            
            if cuenta:
                log.info("Intentando token silencioso para: %s", cuenta.get("username"))
                resultado = self.app.acquire_token_silent(SCOPES_DELEGADOS, account=cuenta)
            
            if not resultado:
                resultado = self._flujo_device_code()
        
        self._guardar_cache()
        
        if "access_token" not in resultado:
            error = resultado.get("error", "")
            desc = resultado.get("error_description", "")
            raise RuntimeError(f"Fallo de autenticación: {error} | {desc}")
        
        log.info("✅ Token obtenido correctamente (expira en %s s)", resultado.get("expires_in"))
        return resultado["access_token"]
    
    @property
    def base_url(self) -> str:
        """URL base del buzón. Delegado = /me ; App = /users/{correo}."""
        if self.modo == "app" and self.mailbox:
            return f"{GRAPH_URL}/users/{self.mailbox}"
        return f"{GRAPH_URL}/me"
