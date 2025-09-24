from telethon import Button, types
from typing import List, Dict, Any
import logging

# Configurar logging para depuración y auditoría
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename="ui.log"
)

# ---------- Reply Keyboards ----------
def _b(t: str) -> types.KeyboardButton:
    """
    Crea un botón de teclado con el texto especificado.
    
    Args:
        t (str): Texto del botón.
    
    Returns:
        types.KeyboardButton: Botón de Telegram.
    """
    if not t:
        logging.warning("Intento de crear botón con texto vacío.")
        raise ValueError("El texto del botón no puede estar vacío.")
    return types.KeyboardButton(text=t)

def _row(*texts: str) -> types.KeyboardButtonRow:
    """
    Crea una fila de botones para un teclado.
    
    Args:
        texts: Textos de los botones en la fila.
    
    Returns:
        types.KeyboardButtonRow: Fila de botones.
    """
    if not texts:
        logging.warning("Intento de crear fila de botones vacía.")
        raise ValueError("La fila de botones debe contener al menos un botón.")
    return types.KeyboardButtonRow(buttons=[_b(t) for t in texts])

def kb_boss() -> types.ReplyKeyboardMarkup:
    """
    Crea el teclado para el administrador (boss) con opciones de gestión.
    
    Returns:
        types.ReplyKeyboardMarkup: Teclado con botones para resellers, clientes, pagos, facturas y ajustes.
    """
    try:
        return types.ReplyKeyboardMarkup(
            rows=[
                _row("💼 Resellers", "👥 Clientes"),
                _row("💳 Pagos", "🧾 Facturas"),
                _row("⚙️ Ajustes")
            ],
            resize=True
        )
    except Exception as e:
        logging.error(f"Error al crear kb_boss: {e}")
        raise

def kb_reseller() -> types.ReplyKeyboardMarkup:
    """
    Crea el teclado para resellers con opciones de gestión de clientes y pagos.
    
    Returns:
        types.ReplyKeyboardMarkup: Teclado con botones para clientes, creación, pagos y soporte.
    """
    try:
        return types.ReplyKeyboardMarkup(
            rows=[
                _row("👥 Mis clientes", "➕ Crear cliente"),
                _row("💳 Pagar / Renovar", "📞 Soporte Boss")
            ],
            resize=True
        )
    except Exception as e:
        logging.error(f"Error al crear kb_reseller: {e}")
        raise

def kb_client() -> types.ReplyKeyboardMarkup:
    """
    Crea el teclado para clientes con opciones de gestión de su plan y soporte.
    
    Returns:
        types.ReplyKeyboardMarkup: Teclado con botones para plan, provisión, pagos y soporte.
    """
    try:
        return types.ReplyKeyboardMarkup(
            rows=[
                _row("📄 Mi plan", "⚙️ Provisionar"),
                _row("💳 Pagar / Renovar", "📞 Soporte")
            ],
            resize=True
        )
    except Exception as e:
        logging.error(f"Error al crear kb_client: {e}")
        raise

# ---------- Inline Blocks ----------
def inline_plans_reseller(prices: Dict[str, float], rate: float) -> tuple[str, List[List[Button]]]:
    """
    Crea el texto y los botones inline para seleccionar un plan de reseller.
    
    Args:
        prices (Dict[str, float]): Diccionario con precios de planes (res_b, res_p, res_e).
        rate (float): Tasa de cambio USD a CUP.
    
    Returns:
        tuple[str, List[List[Button]]]: Texto con los planes y lista de botones inline.
    
    Raises:
        ValueError: Si faltan precios o la tasa es inválida.
    """
    try:
        if not prices or not all(k in prices for k in ("res_b", "res_p", "res_e")):
            logging.error("Precios incompletos para inline_plans_reseller.")
            raise ValueError("Faltan precios para los planes de reseller.")
        if rate <= 0:
            logging.error(f"Tasa de cambio inválida: {rate}")
            raise ValueError("La tasa de cambio debe ser mayor a 0.")

        text = (
            "🏷 **Elige tu plan de Reseller**\n\n"
            f"• **Básico**: {prices['res_b']} USD / {_fmt_money_cup(prices['res_b'] * rate)}\n"
            f"• **Pro**: {prices['res_p']} USD / {_fmt_money_cup(prices['res_p'] * rate)}\n"
            f"• **Enterprise**: {prices['res_e']} USD / {_fmt_money_cup(prices['res_e'] * rate)}\n\n"
            "Selecciona un plan para continuar:"
        )
        buttons = [
            [
                Button.inline("Básico", b"pay:res_b"),
                Button.inline("Pro", b"pay:res_p"),
                Button.inline("Enterprise", b"pay:res_e")
            ],
            [Button.inline("« Volver atrás", b"pay:back")]
        ]
        logging.info("Botones inline de planes de reseller generados correctamente.")
        return text, buttons
    except Exception as e:
        logging.error(f"Error en inline_plans_reseller: {e}")
        raise

def inline_pay_methods(usd: float, cup: float) -> tuple[str, List[List[Button]]]:
    """
    Crea el texto y los botones inline para seleccionar el método de pago.
    
    Args:
        usd (float): Monto en USD.
        cup (float): Monto en CUP (calculado con la tasa de cambio).
    
    Returns:
        tuple[str, List[List[Button]]]: Texto con el monto y lista de botones inline.
    
    Raises:
        ValueError: Si los montos son inválidos.
    """
    try:
        if usd <= 0 or cup <= 0:
            logging.error(f"Montos inválidos: USD={usd}, CUP={cup}")
            raise ValueError("Los montos USD y CUP deben ser mayores a 0.")
        
        text = (
            "💰 **Confirmar pago**\n\n"
            f"• Monto: **{usd} USD** ({_fmt_money_cup(cup)})\n"
            "Selecciona el método de pago:"
        )
        buttons = [
            [Button.inline("Saldo", b"pay:m:saldo"), Button.inline("CUP", b"pay:m:cup")],
            [Button.inline("« Volver atrás", b"pay:plan")]
        ]
        logging.info(f"Botones inline de métodos de pago generados: USD={usd}, CUP={cup}")
        return text, buttons
    except Exception as e:
        logging.error(f"Error en inline_pay_methods: {e}")
        raise

def inline_client_terms(prices: Dict[str, float]) -> tuple[str, List[List[Button]]]:
    """
    Crea el texto y los botones inline para seleccionar la duración de renovación de un cliente.
    
    Args:
        prices (Dict[str, float]): Diccionario con precios de planes de cliente (c30, c90, c365).
    
    Returns:
        tuple[str, List[List[Button]]]: Texto con las duraciones y lista de botones inline.
    
    Raises:
        ValueError: Si faltan precios de planes.
    """
    try:
        if not prices or not all(k in prices for k in ("c30", "c90", "c365")):
            logging.error("Precios incompletos para inline_client_terms.")
            raise ValueError("Faltan precios para los planes de cliente.")
        
        text = (
            "🗓 **Renovar plan de cliente**\n\n"
            f"• 30 días: **{prices['c30']} USD**\n"
            f"• 90 días: **{prices['c90']} USD**\n"
            f"• 365 días: **{prices['c365']} USD**\n\n"
            "Selecciona la duración del plan:"
        )
        buttons = [
            [
                Button.inline("30 días", b"pay:c:30"),
                Button.inline("90 días", b"pay:c:90"),
                Button.inline("365 días", b"pay:c:365")
            ],
            [Button.inline("« Volver atrás", b"pay:back")]
        ]
        logging.info("Botones inline de términos de cliente generados correctamente.")
        return text, buttons
    except Exception as e:
        logging.error(f"Error en inline_client_terms: {e}")
        raise

def inline_pick_client(slugs: List[str]) -> List[List[Button]]:
    """
    Crea botones inline para seleccionar un cliente a partir de su slug.
    
    Args:
        slugs (List[str]): Lista de slugs de clientes.
    
    Returns:
        List[List[Button]]: Lista de filas de botones inline.
    
    Raises:
        ValueError: Si la lista de slugs está vacía.
    """
    try:
        if not slugs:
            logging.warning("Lista de slugs vacía en inline_pick_client.")
            raise ValueError("No hay clientes para seleccionar.")
        
        rows, row = [], []
        for s in slugs:
            row.append(Button.inline(f"👤 {s}", f"pay:cli:{s}".encode()))
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append([Button.inline("« Volver atrás", b"pay:back")])
        logging.info(f"Botones inline para {len(slugs)} clientes generados.")
        return rows
    except Exception as e:
        logging.error(f"Error en inline_pick_client: {e}")
        raise

def btn_send_receipt() -> List[List[Button]]:
    """
    Crea botones inline para enviar un comprobante de pago.
    
    Returns:
        List[List[Button]]: Lista de botones inline.
    """
    try:
        buttons = [
            [Button.inline("📤 Enviar comprobante", b"pay:receipt")],
            [Button.inline("« Volver atrás", b"pay:back")]
        ]
        logging.info("Botones inline de comprobante generados.")
        return buttons
    except Exception as e:
        logging.error(f"Error en btn_send_receipt: {e}")
        raise

# ---------- Pretty Formatters ----------
STATE_ICON = {
    "active": "🟢 Activo",
    "stopped": "🔴 Pausado",
    "unknown": "⚪ Desconocido"
}
STATUS_ICON = {
    "pending": "⏳ Pendiente",
    "approved": "✅ Aprobado",
    "rejected": "❌ Rechazado"
}

def _fmt_money_cup(x: float) -> str:
    """
    Formatea un monto en CUP con separadores de miles.
    
    Args:
        x (float): Monto a formatear.
    
    Returns:
        str: Monto formateado (ej. "1,234 CUP").
    """
    try:
        return f"{int(x):,} CUP".replace(",", " ")
    except ValueError:
        logging.error(f"Error al formatear monto CUP: {x}")
        return "0 CUP"

def fmt_payments_pretty(rows: List[Dict[str, Any]]) -> str:
    """
    Formatea una lista de pagos en un texto legible para el administrador.
    
    Args:
        rows (List[Dict[str, Any]]): Lista de pagos con sus detalles.
    
    Returns:
        str: Texto formateado con los pagos.
    """
    try:
        if not rows:
            return "🧾 **Pagos recientes**\n\nNo hay pagos registrados."
        out = ["🧾 **Pagos recientes**\n"]
        for r in rows:
            out += [
                f"🔸 **ID**: `{r['id']}`",
                f"   📌 **Estado**: {STATUS_ICON.get(r['status'], r['status'])}",
                f"   💵 **Monto**: {r['amount_usd']} USD",
                f"   💱 **Equivalente**: {_fmt_money_cup(r['amount_cup'])}",
                f"   👤 **Plan/Concepto**: {r['plan']}",
                f"   🛒 **Item**: `{r['item_id']}`",
                f"   🆔 **Usuario**: `{r['user_id']}`",
                ""
            ]
        out.append("⚙️ **Comandos disponibles**:\n- `/approve <id>`\n- `/reject <id> <motivo>`")
        logging.info(f"Formateo de {len(rows)} pagos completado.")
        return "\n".join(out)
    except Exception as e:
        logging.error(f"Error en fmt_payments_pretty: {e}")
        return "🧾 **Error al mostrar pagos**\nNo se pudieron formatear los pagos."

def fmt_resellers_list(rows: List[Dict[str, Any]]) -> str:
    """
    Formatea una lista de resellers en un texto legible para el administrador.
    
    Args:
        rows (List[Dict[str, Any]]): Lista de resellers con sus detalles.
    
    Returns:
        str: Texto formateado con los resellers.
    """
    try:
        if not rows:
            return "💼 **Resellers**\n\nNo hay resellers registrados."
        out = ["💼 **Lista de Resellers**\n"]
        for r in rows:
            out.append(
                f"🔹 **ID**: `{r['id']}` | **Plan**: {r['plan']} | **Vence**: {r['expires']} | "
                f"**Contacto**: {r.get('contact', 'N/A')} | **Clientes**: {r.get('clients', 0)}"
            )
        logging.info(f"Formateo de {len(rows)} resellers completado.")
        return "\n".join(out)
    except Exception as e:
        logging.error(f"Error en fmt_resellers_list: {e}")
        return "💼 **Error al mostrar resellers**\nNo se pudieron formatear los resellers."

def fmt_clients_list(rows: List[Dict[str, Any]], title: str = "👥 CLIENTES") -> str:
    """
    Formatea una lista de clientes en un texto legible.
    
    Args:
        rows (List[Dict[str, Any]]): Lista de clientes con sus detalles.
        title (str): Título del listado (por defecto, "CLIENTES").
    
    Returns:
        str: Texto formateado con los clientes.
    """
    try:
        if not rows:
            return f"{title}\n\nNo hay clientes registrados."
        out = [f"{title}\n"]
        for c in rows:
            out.append(
                f"🔹 **Slug**: `{c['slug']}` | **Plan**: {c['plan']} | **Vence**: {c['expires']} | "
                f"**Reseller**: `{c['reseller_id']}`"
            )
        logging.info(f"Formateo de {len(rows)} clientes completado.")
        return "\n".join(out)
    except Exception as e:
        logging.error(f"Error en fmt_clients_list: {e}")
        return f"{title}\n\nError al mostrar los clientes."

def fmt_client_card(c: Dict[str, Any]) -> str:
    """
    Formatea los detalles de un cliente en una tarjeta informativa.
    
    Args:
        c (Dict[str, Any]): Detalles del cliente.
    
    Returns:
        str: Texto formateado con la información del cliente.
    """
    try:
        return (
            "👤 **Información del Cliente**\n\n"
            f"🧭 **Slug**: `{c['slug']}`\n"
            f"🆔 **Propietario**: `{c['owner_id']}` (@{c.get('username', 'N/A')})\n"
            f"💼 **Reseller**: `{c['reseller_id']}`\n"
            f"🏷 **Plan**: {c['plan']}\n"
            f"📅 **Vence**: {c['expires']}\n"
            f"🗂 **Directorio**: `{c['workdir']}`\n"
            f"🛰 **Estado del servicio**: {STATE_ICON.get(c.get('svc_status', 'unknown'), 'Desconocido')}"
        )
    except Exception as e:
        logging.error(f"Error en fmt_client_card: {e}")
        return "👤 **Error al mostrar cliente**\nNo se pudieron formatear los datos."

def fmt_status_panel(s: Dict[str, Any]) -> str:
    """
    Formatea el panel de estado de un cliente o servicio.
    
    Args:
        s (Dict[str, Any]): Detalles del estado del cliente o servicio.
    
    Returns:
        str: Texto formateado con el estado.
    """
    try:
        return (
            "📊 **Estado del Servicio**\n\n"
            f"🏷 **Plan**: {s['plan']}\n"
            f"🧭 **Slug**: `{s['slug']}`\n"
            f"📅 **Vence**: {s['expires']}\n"
            f"🛰 **Servicio**: {STATE_ICON.get(s.get('svc', 'unknown'), 'Desconocido')}\n"
            f"🤖 **Bot**: @{s.get('bot', 'No configurado')}\n"
            f"📁 **Directorio**: `{s['workdir']}`"
        )
    except Exception as e:
        logging.error(f"Error en fmt_status_panel: {e}")
        return "📊 **Error al mostrar estado**\nNo se pudieron formatear los datos."

# ---------- Messages ----------
MSG_CLIENT_WELCOME = (
    "🚀 **Bienvenido a tu Panel de Servicio**\n\n"
    "🔖 **Plan**: {plan}\n"
    "📅 **Vence**: {expires}\n"
    "🧭 **ID**: `{slug}`\n\n"
    "💡 Usa **💳 Pagar / Renovar** para mantener tu servicio activo o **📞 Soporte** para ayuda."
)
MSG_RES_LIMIT = (
    "⛔ **Límite de clientes alcanzado**\n"
    "Tu plan permite un máximo de {limit} clientes.\n"
    "Actualiza tu plan en **💳 Pagar / Renovar** para crear más."
)
MSG_PAY_PICK = (
    "💳 **Realizar un pago**\n\n"
    "Selecciona una opción:\n"
    "• **Plan Reseller**: Actualiza o renueva tu plan (Básico, Pro, Enterprise).\n"
    "• **Renovar Cliente**: Extiende el plan de un cliente existente (30, 90 o 365 días)."
)
MSG_PAY_SALDO = (
    "💵 **Pagar con saldo**\n\n"
    "{txt}\n"
    "Monto: **{monto_saldo} CUP**\n\n"
    "1. Realiza el pago.\n"
    "2. Pulsa **📤 Enviar comprobante** y adjunta la captura en el chat."
)
MSG_PAY_CUP = (
    "💵 **Pagar en CUP**\n\n"
    "{txt}\n"
    "Monto: **{monto_cup} CUP**\n\n"
    "1. Realiza el pago.\n"
    "2. Pulsa **📤 Enviar comprobante** y adjunta la captura en el chat."
)
MSG_RECEIPT_OK = (
    "✅ **Comprobante recibido**\n"
    "Tu pago está en revisión. El administrador lo aprobará pronto.\n"
    "Te notificaremos cuando esté listo."
)
MSG_EXPIRES_TMR = (
    "⚠️ **Recordatorio: ¡Tu servicio vence mañana!**\n"
    "• **ID**: `{slug}`\n"
    "• **Fecha**: {expires}\n\n"
    "Renueva ahora en **💳 Pagar / Renovar** para evitar interrupciones."
)
MSG_EXPIRED = (
    "🔴 **Servicio pausado por vencimiento**\n"
    "• **ID**: `{slug}`\n"
    "• **Venció**: {expires}\n\n"
    "Renueva en **💳 Pagar / Renovar** para reactivar tu servicio."
)
MSG_CREATED_CLIENT = (
    "✅ **Cliente creado exitosamente**\n"
    "• **Slug**: `{slug}`\n"
    "• **Reseller**: `{rid}`\n"
    "• **Vence**: `{expires}`\n\n"
    "Notifica al cliente con su slug para que pueda usar el servicio."
)
MSG_CREATED_RESELLER = (
    "✅ **Reseller activado**\n"
    "• **ID**: `{rid}`\n"
    "• **Plan**: Básico\n"
    "• **Vence**: `{expires}`\n\n"
    "¡Listo para crear clientes y vender! Usa **👥 Mis clientes** o **➕ Crear cliente**."
        )
