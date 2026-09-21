# 🏢 Guía Práctica para Proveedores: Trámite de Contraseñas Automáticas

Estimado proveedor, con el fin de agilizar sus pagos y garantizar que sus contraseñas se generen el mismo día, hemos automatizado nuestra recepción de facturas. 

Para que nuestro lector robótico (OCR) apruebe su trámite sin demoras, es **estrictamente necesario** cumplir con las siguientes instrucciones y ejemplos.

---

## 1. Regla de Oro: Un trámite = Un correo
Para evitar que sus documentos se traspapelen, procesamos cada pago individualmente.

> [!CAUTION]
> **REGLA ESTRICTA:** Si usted tiene múltiples facturas por cobrar, **deberá enviar múltiples correos por separado** (Un correo por cada factura con su respectiva Orden de Compra). Los correos que contengan 2 o más facturas mezcladas serán devueltos.

---

## 2. El Correo Electrónico
El bot escanea la bandeja de entrada buscando palabras clave. 

✅ **Ejemplos de Asuntos CORRECTOS:**
* *Contraseña de Pago - GPS Tecnología - Fact. 123*
* *Trámite de contraseña - Repuestos S.A.*
* *Solicitud de contraseñas de OC 44021194*

❌ **Ejemplos de Asuntos INCORRECTOS:**
* *Envío documentos* (Será ignorado, falta la palabra "contraseña")
* *Hola, adjunto mi factura* (Será ignorado)

---

## 3. Los Archivos Adjuntos (El formato es clave)
El sistema extrae el texto directamente de los archivos. 

✅ **Formato Aceptado:**
* **PDF Nativos:** Archivos exportados directamente de su sistema contable (Word, Excel, o su ERP).
* **Nombres lógicos:** `Factura_1234.pdf` y `Orden_4402.pdf`. (O puede ser un solo PDF que contenga ambas páginas).

❌ **Formatos RECHAZADOS automáticamente:**
* Archivos comprimidos `.ZIP` o `.RAR`.
* Enlaces de descarga de Google Drive, OneDrive o WeTransfer.
* Fotos tomadas con el celular (`.JPG`, `.PNG`) insertadas en el cuerpo del correo.
* Escaneos borrosos, torcidos, con sombras oscuras o marcas de agua que tapen los números.

---

## 4. Ejemplos de Contenido en los Documentos
Nuestro robot busca palabras exactas en sus PDFs. Si no encuentra estas frases, su trámite se rechazará automáticamente por "Falta de Información".

### A) La Orden de Compra (OC)
El documento de la Orden de Compra debe tener visible el número de la orden y el nombre de quien autoriza.

> **✅ TEXTO ESPERADO EN EL PDF:**
> * "Orden de compra número: **44021194**" (o también es válido "OC: 44021194")
> * "OC realizada por: **Juan Pérez** - jperez@canella.com.gt"

> **❌ LO QUE CAUSARÁ RECHAZO:**
> * Poner solo un número suelto sin decir qué es (Ej. Solo poner `44021194` en una esquina). El robot no sabrá que eso es la OC.

### B) La Factura
El PDF de su factura debe incluir claramente el número de factura y su NIT.

> **✅ TEXTO ESPERADO EN EL PDF:**
> * "Factura No. **12345**"
> * "NIT: **123456-7**"
> * "Total a pagar: **Q 1,500.00**"

> **❌ LO QUE CAUSARÁ RECHAZO:**
> * Facturas donde el NIT de su empresa no está impreso en el documento.
> * Facturas donde el número de factura está cortado por un mal escaneo o tapado por una firma o sello de recibido.

---

### 📥 Resumen Final de Envío Ideal
Si usted cumple con el siguiente "Checklist", su pago entrará al sistema en menos de 1 minuto:

1. [ ] ¿Envié un solo correo por esta factura?
2. [ ] ¿El asunto del correo incluye la palabra "Contraseña"?
3. [ ] ¿Adjunté la Factura y la OC en archivos PDF?
4. [ ] ¿Están legibles los números de Orden y de Factura en los documentos?

¡Agradecemos mucho su apoyo cumpliendo estos lineamientos! Esto nos permitirá garantizarle un trámite de pago mucho más rápido y sin errores manuales.
