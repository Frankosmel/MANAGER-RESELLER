import asyncio
import datetime as dt
from telethon import TelegramClient, events, Button
from .config import SET
from .models_db import (
    init_db, cx, get_setting, set_setting, role_for, limits, prices,
    prorate, ensure_client_workdir, slugify, new_id, iso_now
)
from .ui import (
    kb_boss, kb_reseller, kb_client,
    inline_plans_reseller, inline_pay_methods, inline_client_terms, inline_pick_client,
    btn_send_receipt, inline_client_plans,  # Nueva función para planes de cliente
    fmt_clients_list, fmt_payments_pretty, fmt_client_card,
    MSG_WELCOME_GUEST, MSG_WELCOME_BOSS, MSG_WELCOME_RESELLER, MSG_WELCOME_CLIENT,
    MSG_ERROR_NO_PERMISSION, MSG_ERROR_INVALID_ID,
    MSG_CLIENT_CREATED, MSG_RESELLER_CREATED,
    MSG_PAYMENT_PICK, MSG_PAYMENT_SALDO, MSG_PAYMENT_CUP, MSG_PAYMENT_SUCCESS,
    MSG_EXPIRES_TOMORROW, MSG_EXPIRED, MSG_RES_LIMIT
)
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename=str(SET.data_dir / "logs" / "bot.log")
)

# Inicializar cliente de Telegram
bot = TelegramClient("reseller_mgr", SET.api_id, SET.api_hash)
flows = {}  # Diccionario para almacenar el estado de conversación por usuario

async def reply(ev, message: str, buttons=None, parse_mode: str = "markdown") -> None:
    """
    Enviar un mensaje con formato Markdown y botones opcionales.
    
    Args:
        ev: Evento de Telegram (mensaje o callback).
        message: Mensaje a enviar.
        buttons: Botones opcionales (ReplyKeyboard o InlineKeyboard).
        parse_mode: Formato del mensaje (por defecto, Markdown).
    """
    try:
        await ev.reply(message, buttons=buttons or Button.clear(), parse_mode=parse_mode)
        logging.info(f"Mensaje enviado a {ev.sender_id}: {message[:50]}...")
    except Exception as e:
        logging.error(f"Error al enviar mensaje a {ev.sender_id}: {e}")

# ---------- /start ----------
@bot.on(events.NewMessage(pattern=r"^/start$"))
async def start(ev):
    """
    Maneja el comando /start y muestra el panel correspondiente según el rol del usuario.
    
    - Guest: Indica cómo registrarse.
    - Boss: Muestra el panel de administrador.
    - Reseller: Muestra el panel de reseller.
    - Client: Muestra detalles del plan del cliente.
    """
    init_db()
    user_id = ev.sender_id
    role = role_for(user_id)
    logging.info(f"Comando /start ejecutado por {user_id} (rol: {role})")

    if role == "guest":
        support_contact = get_setting("support_contact", "soporte")
        await reply(ev, MSG_WELCOME_GUEST.format(support_contact=support_contact))
        return
    if role == "boss":
        await reply(ev, MSG_WELCOME_BOSS, kb_boss())
        return
    if role == "reseller":
        await reply(ev, MSG_WELCOME_RESELLER, kb_reseller())
        return
    if role == "client":
        with cx() as c:
            cur = c.cursor()
            cur.execute("SELECT slug, plan, expires, username FROM clients WHERE owner_id=?", (user_id,))
            row = cur.fetchone()
        if row:
            username = row["username"] or f"Usuario {user_id}"
            await reply(ev, MSG_WELCOME_CLIENT.format(
                username=username, plan=row["plan"], expires=row["expires"], slug=row["slug"]
            ), kb_client())
        else:
            await reply(ev, "❌ **Error**: No se encontraron detalles de tu plan. Contacta a soporte.", kb_client())
        return

# ---------- Configurar Owner ----------
@bot.on(events.NewMessage(pattern=r"^/set_owner\s+(\d+)$"))
async def set_owner(ev):
    """
    Establece el dueño del sistema (solo si no hay dueño o lo ejecuta el dueño actual).
    
    Args:
        ev: Evento con el comando /set_owner <id>.
    """
    current = int(get_setting("owner_id", "0") or 0)
    if current not in (0, ev.sender_id):
        await reply(ev, MSG_ERROR_NO_PERMISSION)
        return
    new_owner_id = ev.pattern_match.group(1)
    try:
        await bot.get_entity(int(new_owner_id))
        set_setting("owner_id", new_owner_id)
        await reply(ev, f"👑 **Dueño establecido**\nID: `{new_owner_id}`\nEl sistema está ahora bajo tu control.", kb_boss())
        logging.info(f"Nuevo dueño establecido: {new_owner_id}")
    except ValueError:
        await reply(ev, MSG_ERROR_INVALID_ID)
        logging.error(f"Intento de set_owner con ID inválido: {new_owner_id}")

# ---------- Boss: Crear Reseller ----------
@bot.on(events.NewMessage(pattern=r"^/reseller_add\s+(\d+)$"))
async def reseller_add(ev):
    """
    Crea un nuevo reseller con un plan básico y 30 días de validez (solo boss).
    
    Args:
        ev: Evento con el comando /reseller_add <id>.
    """
    if role_for(ev.sender_id) != "boss":
        await reply(ev, MSG_ERROR_NO_PERMISSION)
        return
    rid = ev.pattern_match.group(1)
    try:
        await bot.get_entity(int(rid))
        today = dt.date.today().isoformat()
        expires = (dt.date.today() + dt.timedelta(days=30)).isoformat()
        with cx() as c:
            cur = c.cursor()
            cur.execute(
                """INSERT OR REPLACE INTO resellers(id, plan, started, expires, contact)
                   VALUES (?, ?, ?, ?, ?)""",
                (rid, "res_b", today, expires, "@contacto")
            )
            c.commit()
        await reply(ev, MSG_RESELLER_CREATED.format(rid=rid, plan="res_b", expires=expires), kb_boss())
        logging.info(f"Reseller creado: ID={rid}, plan=res_b, vence={expires}")
    except ValueError:
        await reply(ev, MSG_ERROR_INVALID_ID)
        logging.error(f"Intento de reseller_add con ID inválido: {rid}")

# ---------- Boss: Actualizar Contacto de Reseller ----------
@bot.on(events.NewMessage(pattern=r"^/reseller_contact\s+(\d+)\s+(@\S+)$"))
async def reseller_contact(ev):
    """
    Actualiza el contacto de un reseller (solo boss).
    
    Args:
        ev: Evento con el comando /reseller_contact <id> <contacto>.
    """
    if role_for(ev.sender_id) != "boss":
        await reply(ev, MSG_ERROR_NO_PERMISSION)
        return
    rid = ev.pattern_match.group(1)
    tag = ev.pattern_match.group(2)
    if not tag.startswith("@") or len(tag) < 3:
        await reply(ev, "❌ **Error**: El contacto debe ser un @usuario válido (ej. @Soporte).")
        logging.error(f"Contacto inválido para reseller {rid}: {tag}")
        return
    with cx() as c:
        cur = c.cursor()
        cur.execute("SELECT 1 FROM resellers WHERE id=?", (rid,))
        if not cur.fetchone():
            await reply(ev, f"❌ **Error**: No existe un reseller con ID `{rid}`.")
            logging.error(f"Reseller no encontrado: {rid}")
            return
        cur.execute("UPDATE resellers SET contact=? WHERE id=?", (tag, rid))
        c.commit()
    await reply(ev, f"📞 **Contacto actualizado**\nReseller `{rid}` ahora tiene contacto: `{tag}`.", kb_boss())
    logging.info(f"Contacto actualizado para reseller {rid}: {tag}")

# ---------- Boss: Listar todos los clientes ----------
@bot.on(events.NewMessage(pattern=r"^👥 Clientes$"))
async def boss_clients(ev):
    """
    Muestra la lista de todos los clientes del sistema (solo boss).
    
    Args:
        ev: Evento con el comando "Clientes".
    """
    if role_for(ev.sender_id) != "boss":
        await reply(ev, MSG_ERROR_NO_PERMISSION)
        return
    with cx() as c:
        cur = c.cursor()
        cur.execute("SELECT slug, plan, expires, reseller_id FROM clients ORDER BY slug")
        rows = cur.fetchall()
    await reply(ev, fmt_clients_list(rows, "👥 **Todos los Clientes del Sistema**"), kb_boss())
    logging.info(f"Lista de clientes solicitada por boss {ev.sender_id}")

# ---------- Boss: Mostrar facturas (pagos aprobados) ----------
@bot.on(events.NewMessage(pattern=r"^🧾 Facturas$"))
async def boss_invoices(ev):
    """
    Muestra los últimos 30 pagos aprobados como facturas (solo boss).
    
    Args:
        ev: Evento con el comando "Facturas".
    """
    if role_for(ev.sender_id) != "boss":
        await reply(ev, MSG_ERROR_NO_PERMISSION)
        return
    with cx() as c:
        cur = c.cursor()
        cur.execute("SELECT * FROM payments WHERE status='approved' ORDER BY created DESC LIMIT 30")
        rows = cur.fetchall()
    await reply(ev, fmt_payments_pretty(rows), kb_boss())
    logging.info(f"Lista de facturas solicitada por boss {ev.sender_id}")

# ---------- Boss: Mostrar ajustes ----------
@bot.on(events.NewMessage(pattern=r"^⚙️ Ajustes$"))
async def boss_settings(ev):
    """
    Muestra las configuraciones actuales (precios, tasas, límites) al boss.
    
    Args:
        ev: Evento con el comando "Ajustes".
    """
    if role_for(ev.sender_id) != "boss":
        await reply(ev, MSG_ERROR_NO_PERMISSION)
        return
    with cx() as c:
        cur = c.cursor()
        pr = prices(cur)
        lim = limits(cur)
    text = (
        "⚙️ **Ajustes actuales**\n\n"
        f"💱 **Tasa USD→CUP**: {pr['usd_to_cup']}\n\n"
        "🏷 **Precios Reseller (USD)**:\n"
        f"• Básico: {pr['res_b']}\n"
        f"• Pro: {pr['res_p']}\n"
        f"• Enterprise: {pr['res_e']}\n\n"
        "🗓 **Precios Clientes (USD)**:\n"
        f"• 30 días: {pr['c30']}\n"
        f"• 90 días: {pr['c90']}\n"
        f"• 365 días: {pr['c365']}\n\n"
        "🚫 **Límites Reseller**:\n"
        f"• Básico: {lim['res_b']}\n"
        f"• Pro: {lim['res_p']}\n"
        f"• Enterprise: {lim['res_e']}\n\n"
        "Usa comandos como /set_rate o /set_price para cambiarlos."
    )
    await reply(ev, text, kb_boss())
    logging.info(f"Ajustes solicitados por boss {ev.sender_id}")

# ---------- Boss: Crear cliente ----------
@bot.on(events.NewMessage(pattern=r"^➕ Crear cliente$"))
async def boss_create_client(ev):
    """
    Inicia el proceso de creación de un cliente por el boss.
    
    Args:
        ev: Evento con el comando "Crear cliente".
    """
    if role_for(ev.sender_id) != "boss":
        await reply(ev, MSG_ERROR_NO_PERMISSION)
        return
    flows[ev.sender_id] = {"mode": "newcli_boss", "step": "client_id", "rid": str(ev.sender_id)}
    await reply(ev, "🆕 **Crear Cliente como Boss**\nEnvía el **ID numérico** del cliente final:", kb_boss())
    logging.info(f"Boss {ev.sender_id} inició flujo de creación de cliente")

# ---------- Client: Mostrar mi plan ----------
@bot.on(events.NewMessage(pattern=r"^📄 Mi plan$"))
async def cli_my_plan(ev):
    """
    Muestra los detalles del plan del cliente.
    
    Args:
        ev: Evento con el comando "Mi plan".
    """
    if role_for(ev.sender_id) != "client":
        await reply(ev, MSG_ERROR_NO_PERMISSION)
        return
    with cx() as c:
        cur = c.cursor()
        cur.execute("SELECT * FROM clients WHERE owner_id=?", (ev.sender_id,))
        row = cur.fetchone()
    if not row:
        await reply(ev, "❌ **Error**: No tienes un plan registrado.", kb_client())
        logging.error(f"Cliente {ev.sender_id} no encontrado en la base de datos")
        return
    await reply(ev, fmt_client_card(row), kb_client())
    logging.info(f"Detalles del plan mostrados para cliente {ev.sender_id}")

# ---------- Client: Provisionar (toggle estado del servicio) ----------
@bot.on(events.NewMessage(pattern=r"^⚙️ Provisionar$"))
async def cli_provision(ev):
    """
    Alterna el estado del servicio del cliente (active/stopped).
    
    Args:
        ev: Evento con el comando "Provisionar".
    """
    if role_for(ev.sender_id) != "client":
        await reply(ev, MSG_ERROR_NO_PERMISSION)
        return
    with cx() as c:
        cur = c.cursor()
        cur.execute("SELECT slug, svc_status FROM clients WHERE owner_id=?", (ev.sender_id,))
        row = cur.fetchone()
        if not row:
            await reply(ev, "❌ **Error**: No tienes un plan registrado.", kb_client())
            logging.error(f"Cliente {ev.sender_id} no encontrado para provisionar")
            return
        new_status = "active" if row["svc_status"] == "stopped" else "stopped"
        cur.execute("UPDATE clients SET svc_status=? WHERE slug=?", (new_status, row["slug"]))
        c.commit()
    await reply(ev, f"⚙️ **Servicio {new_status}**\nSlug: `{row['slug']}`.\nUsa **📄 Mi plan** para verificar.", kb_client())
    logging.info(f"Servicio provisionado para cliente {ev.sender_id}: {new_status}")

# ---------- Configurar Tasas y Precios ----------
@bot.on(events.NewMessage(pattern=r"^/set_rate\s+(\d+(\.\d+)?)$"))
async def set_rate(ev):
    """
    Actualiza la tasa de cambio USD a CUP (solo boss).
    
    Args:
        ev: Evento con el comando /set_rate <tasa>.
    """
    if role_for(ev.sender_id) != "boss":
        await reply(ev, MSG_ERROR_NO_PERMISSION)
        return
    rate = float(ev.pattern_match.group(1))
    if rate <= 0:
        await reply(ev, "❌ **Error**: La tasa debe ser un número positivo.")
        logging.error(f"Intento de set_rate con valor inválido: {rate}")
        return
    set_setting("usd_to_cup", rate)
    await reply(ev, f"💱 **Tasa actualizada**\nNueva tasa USD→CUP: `{rate}`.", kb_boss())
    logging.info(f"Tasa USD→CUP actualizada a {rate} por boss {ev.sender_id}")

@bot.on(events.NewMessage(pattern=r"^/set_price\s+(res_b|res_p|res_e|c30|c90|c365)\s+(\d+(\.\d+)?)$"))
async def set_price(ev):
    """
    Actualiza el precio de un plan (solo boss).
    
    Args:
        ev: Evento con el comando /set_price <plan> <precio>.
    """
    if role_for(ev.sender_id) != "boss":
        await reply(ev, MSG_ERROR_NO_PERMISSION)
        return
    key = ev.pattern_match.group(1)
    val = float(ev.pattern_match.group(2))
    if val < 0:
        await reply(ev, "❌ **Error**: El precio debe ser no negativo.")
        logging.error(f"Intento de set_price con valor inválido: {val} para {key}")
        return
    mapk = {
        "res_b": "price_res_b", "res_p": "price_res_p", "res_e": "price_res_e",
        "c30": "price_client_30", "c90": "price_client_90", "c365": "price_client_365"
    }[key]
    set_setting(mapk, val)
    await reply(ev, f"💵 **Precio actualizado**\nPlan `{key}` establecido en `{val}` USD.", kb_boss())
    logging.info(f"Precio actualizado para {key}: {val} por boss {ev.sender_id}")

# ---------- Vistas (Reply Keyboard) ----------
@bot.on(events.NewMessage(pattern=r"^💼 Resellers$"))
async def boss_resellers(ev):
    """
    Muestra la lista de resellers al administrador.
    
    Args:
        ev: Evento con el comando "Resellers".
    """
    if role_for(ev.sender_id) != "boss":
        await reply(ev, MSG_ERROR_NO_PERMISSION)
        return
    with cx() as c:
        cur = c.cursor()
        cur.execute("SELECT id, plan, expires, contact, (SELECT COUNT(*) FROM clients WHERE reseller_id=resellers.id) AS clients FROM resellers ORDER BY id")
        rows = cur.fetchall()
    await reply(ev, fmt_resellers_list(rows), kb_boss())
    logging.info(f"Lista de resellers solicitada por boss {ev.sender_id}")

@bot.on(events.NewMessage(pattern=r"^👥 Mis clientes$"))
async def res_my_clients(ev):
    """
    Muestra la lista de clientes de un reseller.
    
    Args:
        ev: Evento con el comando "Mis clientes".
    """
    if role_for(ev.sender_id) != "reseller":
        await reply(ev, MSG_ERROR_NO_PERMISSION)
        return
    with cx() as c:
        cur = c.cursor()
        cur.execute("SELECT slug, plan, expires, reseller_id FROM clients WHERE reseller_id=?", (str(ev.sender_id),))
        rows = cur.fetchall()
    await reply(ev, fmt_clients_list(rows), kb_reseller())
    logging.info(f"Lista de clientes solicitada por reseller {ev.sender_id}")

@bot.on(events.NewMessage(pattern=r"^📞 Soporte Boss$"))
async def res_support_boss(ev):
    """
    Muestra el contacto del boss al reseller.
    
    Args:
        ev: Evento con el comando "Soporte Boss".
    """
    if role_for(ev.sender_id) != "reseller":
        await reply(ev, MSG_ERROR_NO_PERMISSION)
        return
    boss_id = get_setting("owner_id", "")
    tag = f"@{boss_id}" if boss_id and boss_id.isdigit() else "No disponible"
    await reply(ev, f"📞 **Contacto del Boss**\nEscribe a: {tag}", kb_reseller())
    logging.info(f"Soporte boss solicitado por reseller {ev.sender_id}")

@bot.on(events.NewMessage(pattern=r"^📞 Soporte$"))
async def cli_support(ev):
    """
    Muestra el contacto del reseller al cliente.
    
    Args:
        ev: Evento con el comando "Soporte".
    """
    if role_for(ev.sender_id) != "client":
        await reply(ev, MSG_ERROR_NO_PERMISSION)
        return
    with cx() as c:
        cur = c.cursor()
        cur.execute("SELECT reseller_id FROM clients WHERE owner_id=?", (ev.sender_id,))
        row = cur.fetchone()
        if not row:
            await reply(ev, "❌ **Error**: No estás registrado como cliente.", kb_client())
            logging.error(f"Cliente {ev.sender_id} no encontrado para soporte")
            return
        rid = row["reseller_id"]
        cur.execute("SELECT contact FROM resellers WHERE id=?", (rid,))
        rr = cur.fetchone()
        contact = rr["contact"] if rr else "No disponible"
    if contact and contact.startswith("@"):
        link = f"https://t.me/{contact.lstrip('@')}"
        await reply(ev, f"📞 **Tu reseller**\nContacta a: {contact}", [[Button.url("💬 Abrir chat", link)]])
    else:
        await reply(ev, f"📞 **Tu reseller**: No disponible\nIntenta de nuevo más tarde.", kb_client())
    logging.info(f"Soporte solicitado por cliente {ev.sender_id}")

# ---------- Entrada de Pagos ----------
@bot.on(events.NewMessage(pattern=r"^💳 Pagar / Renovar$"))
async def pay_entry(ev):
    """
    Inicia el proceso de pago para resellers o clientes.
    
    Args:
        ev: Evento con el comando "Pagar / Renovar".
    """
    role = role_for(ev.sender_id)
    if role not in ("client", "reseller"):
        await reply(ev, MSG_ERROR_NO_PERMISSION)
        return
    flows[ev.sender_id] = {"mode": "pay", "step": "target", "as": ("reseller" if role == "reseller" else "client")}
    await reply(ev, MSG_PAYMENT_PICK, [
        [Button.inline("Plan Reseller", b"pay:plan"), Button.inline("Renovar Cliente", b"pay:client")]
    ])
    logging.info(f"Flujo de pago iniciado por {ev.sender_id} ({role})")

# ---------- Flujos Inline (Pagos y Creación de Clientes) ----------
@bot.on(events.CallbackQuery)
async def cb(ev):
    """
    Maneja las interacciones con botones inline en los flujos de pagos y creación de clientes.
    
    Args:
        ev: Evento de CallbackQuery con datos de la acción seleccionada.
    """
    user_id = ev.sender_id
    role = role_for(user_id)
    data = (ev.data or b"").decode()
    logging.debug(f"Callback recibido de {user_id}: {data}")

    # Seleccionar plan de reseller
    if data == "pay:plan" and user_id in flows and flows[user_id]["mode"] == "pay":
        with cx() as c:
            cur = c.cursor()
            pr = prices(cur)
            rate = pr["usd_to_cup"]
        txt, btn = inline_plans_reseller(pr, rate)
        await ev.edit(txt, buttons=btn)
        logging.info(f"Planes de reseller mostrados a {user_id}")
        return

    # Seleccionar plan específico de reseller
    if data.startswith("pay:res_") and user_id in flows and flows[user_id]["mode"] == "pay":
        code = data.split(":", 1)[1]
        with cx() as c:
            cur = c.cursor()
            pr = prices(cur)
            rate = pr["usd_to_cup"]
            usd = {"res_b": pr["res_b"], "res_p": pr["res_p"], "res_e": pr["res_e"]}[code]
            cup = int(usd * rate)
        flows[user_id].update({"step": "pay_method", "plan_code": code, "amount_usd": usd, "amount_cup": cup, "item_id": str(user_id)})
        txt, btn = inline_pay_methods(usd, cup)
        await ev.edit(txt, buttons=btn)
        logging.info(f"Métodos de pago mostrados a {user_id} para plan {code}")
        return

    # Renovar cliente: elegir cliente
    if data == "pay:client" and user_id in flows and flows[user_id]["mode"] == "pay":
        if role == "client":
            with cx() as c:
                cur = c.cursor()
                cur.execute("SELECT slug FROM clients WHERE owner_id=?", (user_id,))
                row = cur.fetchone()
            if not row:
                await ev.answer("❌ No estás registrado como cliente.", alert=True)
                logging.error(f"Cliente {user_id} no encontrado para renovar")
                return
            flows[user_id]["client_slug"] = row["slug"]
        else:
            with cx() as c:
                cur = c.cursor()
                cur.execute("SELECT slug FROM clients WHERE reseller_id=?", (str(user_id),))
                slugs = [x["slug"] for x in cur.fetchall()]
            if not slugs:
                await ev.answer("📭 No tienes clientes registrados.", alert=True)
                logging.info(f"Reseller {user_id} no tiene clientes para renovar")
                return
            await ev.edit("👥 **Elige un cliente para renovar**:", buttons=inline_pick_client(slugs))
            return
        with cx() as c:
            cur = c.cursor()
            pr = prices(cur)
        txt, btn = inline_client_terms(pr)
        await ev.edit(txt, buttons=btn)
        logging.info(f"Términos de cliente mostrados a {user_id}")
        return

    # Reseller elige cliente
    if data.startswith("pay:cli:") and user_id in flows and flows[user_id]["mode"] == "pay":
        flows[user_id]["client_slug"] = data.split(":", 2)[2]
        with cx() as c:
            cur = c.cursor()
            pr = prices(cur)
        txt, btn = inline_client_terms(pr)
        await ev.edit(txt, buttons=btn)
        logging.info(f"Cliente seleccionado por reseller {user_id}: {flows[user_id]['client_slug']}")
        return

    # Elegir duración del plan de cliente
    if data in ("pay:c:30", "pay:c:90", "pay:c:365") and user_id in flows and flows[user_id]["mode"] == "pay":
        term = data.split(":")[2]
        with cx() as c:
            cur = c.cursor()
            pr = prices(cur)
            rate = pr["usd_to_cup"]
            usd = {"30": pr["c30"], "90": pr["c90"], "365": pr["c365"]}[term]
            cup = int(usd * rate)
        flows[user_id].update({
            "step": "pay_method",
            "plan_code": f"client_{term}",
            "amount_usd": usd,
            "amount_cup": cup,
            "item_id": flows[user_id].get("client_slug")
        })
        txt, btn = inline_pay_methods(usd, cup)
        await ev.edit(txt, buttons=btn)
        logging.info(f"Métodos de pago mostrados a {user_id} para cliente {term} días")
        return

    # Seleccionar método de pago
    if data in ("pay:m:saldo", "pay:m:cup") and user_id in flows and flows[user_id]["mode"] == "pay":
        mtype = "saldo" if data.endswith("saldo") else "cup"
        f = flows[user_id]
        f["method"] = mtype
        f["step"] = "receipt"
        ps = get_setting("pay_text_saldo")
        pc = get_setting("pay_text_cup")
        txt = (MSG_PAYMENT_SALDO.format(txt=ps, monto_saldo=f["amount_cup"]) if mtype == "saldo"
               else MSG_PAYMENT_CUP.format(txt=pc, monto_cup=f["amount_cup"]))
        await ev.edit(txt, buttons=btn_send_receipt())
        logging.info(f"Método de pago seleccionado por {user_id}: {mtype}")
        return

    # Subir comprobante
    if data == "pay:receipt" and user_id in flows and flows[user_id]["mode"] == "pay":
        flows[user_id]["await_receipt"] = True
        await ev.answer("📎 Por favor, adjunta la imagen del comprobante en el chat.", alert=True)
        logging.info(f"{user_id} solicitado para adjuntar comprobante")

    # Seleccionar plan para cliente (boss)
    if data in ("plan:estandar", "plan:plus", "plan:pro") and user_id in flows and flows[user_id]["mode"] == "newcli_boss":
        plan_code = data.split(":")[1]
        flows[user_id]["plan_code"] = f"plan_{plan_code}"
        flows[user_id]["step"] = "duration_select"
        with cx() as c:
            cur = c.cursor()
            pr = prices(cur)
        txt, btn = inline_client_terms(pr)
        await ev.edit(txt, buttons=btn)
        logging.info(f"Plan seleccionado por boss {user_id}: {plan_code}")
        return

    # Seleccionar duración para cliente (boss)
    if data in ("pay:c:30", "pay:c:90", "pay:c:365") and user_id in flows and flows[user_id]["mode"] == "newcli_boss":
        term = data.split(":")[2]
        days = {"30": 30, "90": 90, "365": 365}[term]
        expires = (dt.date.today() + dt.timedelta(days=days)).isoformat()
        with cx() as c:
            cur = c.cursor()
            cur.execute(
                """INSERT INTO clients(slug, owner_id, username, reseller_id, plan, expires, created, workdir, svc_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (flows[user_id]["slug"], flows[user_id]["client_id"], None, flows[user_id]["rid"],
                 flows[user_id]["plan_code"], expires, iso_now(), flows[user_id]["workdir"], "stopped")
            )
            c.commit()
        await ev.edit(MSG_CLIENT_CREATED.format(slug=flows[user_id]["slug"], rid=flows[user_id]["rid"], expires=expires))
        logging.info(f"Cliente creado por boss {user_id}: slug={flows[user_id]['slug']}, plan={flows[user_id]['plan_code']}")
        try:
            await bot.send_message(
                flows[user_id]["client_id"],
                f"🎉 **¡Bienvenido!**\nHas sido registrado como cliente.\nTu slug es `{flows[user_id]['slug']}` y tu plan `{flows[user_id]['plan_code']}` vence el `{expires}`.\nUsa /start para más detalles."
            )
        except Exception:
            logging.warning(f"No se pudo notificar al cliente {flows[user_id]['client_id']}")
        flows.pop(user_id, None)
        return

    # Volver atrás
    if data == "pay:back" and user_id in flows:
        if flows[user_id]["mode"] == "pay":
            flows[user_id]["step"] = "target"
            await ev.edit(MSG_PAYMENT_PICK, buttons=[
                [Button.inline("Plan Reseller", b"pay:plan"), Button.inline("Renovar Cliente", b"pay:client")]
            ])
        elif flows[user_id]["mode"] == "newcli_boss":
            flows[user_id]["step"] = "client_id"
            await ev.edit("🆕 **Crear Cliente como Boss**\nEnvía el **ID numérico** del cliente final:", buttons=kb_boss())
        logging.info(f"{user_id} volvió atrás en el flujo")
        return

# ---------- Entrada de Datos (Texto/Medios) ----------
@bot.on(events.NewMessage)
async def flows_input(ev):
    """
    Maneja entradas de texto o medios en los flujos de conversación (crear cliente, subir comprobante).
    
    Args:
        ev: Evento con el mensaje del usuario.
    """
    user_id = ev.sender_id
    if user_id not in flows:
        return
    f = flows[user_id]

    # Crear cliente (reseller)
    if f.get("mode") == "newcli" and f.get("step") == "client_id":
        try:
            cid = int((ev.raw_text or "").strip())
        except ValueError:
            await reply(ev, MSG_ERROR_INVALID_ID, kb_reseller())
            logging.error(f"ID inválido proporcionado por reseller {user_id}: {ev.raw_text}")
            return
        with cx() as c:
            cur = c.cursor()
            cur.execute("SELECT plan, started, expires FROM resellers WHERE id=?", (f["rid"],))
            reseller = cur.fetchone()
            if not reseller:
                await reply(ev, "❌ **Error**: No eres un reseller válido.", kb_reseller())
                flows.pop(user_id, None)
                logging.error(f"Reseller {user_id} no encontrado")
                return
            lims = limits(cur)
            lim = lims.get(reseller["plan"], 0)
            cur.execute("SELECT COUNT(*) AS n FROM clients WHERE reseller_id=?", (f["rid"],))
            used = cur.fetchone()["n"]
            if lim and used >= lim:
                await reply(ev, MSG_RES_LIMIT.format(limit=lim), kb_reseller())
                flows.pop(user_id, None)
                logging.info(f"Límite de clientes alcanzado por reseller {user_id}: {used}/{lim}")
                return
            slug = slugify(str(cid))
            base = slug
            i = 2
            while True:
                cur.execute("SELECT 1 FROM clients WHERE slug=?", (slug,))
                if not cur.fetchone():
                    break
                slug = f"{base}{i}"
                i += 1
            wdir = ensure_client_workdir(slug)
            expires = (dt.date.today() + dt.timedelta(days=30)).isoformat()
            cur.execute(
                """INSERT INTO clients(slug, owner_id, username, reseller_id, plan, expires, created, workdir, svc_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (slug, cid, None, f["rid"], "plan_estandar", expires, iso_now(), str(wdir), "stopped")
            )
            c.commit()
        await reply(ev, MSG_CLIENT_CREATED.format(slug=slug, rid=f["rid"], expires=expires), kb_reseller())
        logging.info(f"Cliente creado por reseller {user_id}: slug={slug}, vence={expires}")
        try:
            await bot.send_message(
                cid,
                f"🎉 **¡Bienvenido!**\nHas sido registrado como cliente.\nTu slug es `{slug}` y tu plan vence el `{expires}`.\nUsa /start para más detalles."
            )
        except Exception:
            logging.warning(f"No se pudo notificar al cliente {cid}")
        flows.pop(user_id, None)
        return

    # Crear cliente (boss)
    if f.get("mode") == "newcli_boss" and f.get("step") == "client_id":
        try:
            cid = int((ev.raw_text or "").strip())
        except ValueError:
            await reply(ev, MSG_ERROR_INVALID_ID, kb_boss())
            logging.error(f"ID inválido proporcionado por boss {user_id}: {ev.raw_text}")
            return
        with cx() as c:
            cur = c.cursor()
            slug = slugify(str(cid))
            base = slug
            i = 2
            while True:
                cur.execute("SELECT 1 FROM clients WHERE slug=?", (slug,))
                if not cur.fetchone():
                    break
                slug = f"{base}{i}"
                i += 1
            wdir = ensure_client_workdir(slug)
        flows[user_id].update({"client_id": cid, "slug": slug, "workdir": str(wdir), "step": "plan_select"})
        await ev.reply("🏷 **Selecciona el plan para el cliente:**", buttons=inline_client_plans())
        logging.info(f"Boss {user_id} proporcionó ID de cliente: {cid}, slug={slug}")
        return

    # Recepción de comprobante de pago
    if f.get("mode") == "pay" and f.get("await_receipt"):
        if not (ev.photo or ev.document):
            await reply(ev, "📎 **Error**: Por favor, adjunta una imagen del comprobante.")
            logging.error(f"Comprobante inválido enviado por {user_id}")
            return
        with cx() as c:
            cur = c.cursor()
            pid = new_id()
            cur.execute(
                """INSERT INTO payments(id, user_id, role, type, amount_usd, amount_cup, plan, item_id, receipt_msg_id, status, created, rate_used)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (pid, user_id, f["as"], f["method"], f["amount_usd"], f["amount_cup"],
                 f.get("plan_code", "res_b"), str(f.get("item_id") or user_id),
                 ev.message.id, "pending", iso_now(), prices(cur)["usd_to_cup"])
            )
            c.commit()
        await reply(ev, MSG_PAYMENT_SUCCESS.format(
            pid=pid, amount_usd=f["amount_usd"], amount_cup=f["amount_cup"], method=f["method"], plan=f["plan_code"]
        ))
        logging.info(f"Pago registrado por {user_id}: ID={pid}, plan={f['plan_code']}")
        boss_id = int(get_setting("owner_id", "0") or 0)
        if boss_id:
            try:
                await bot.send_message(
                    boss_id,
                    f"🧾 **Nuevo pago pendiente**\n- Usuario: `{user_id}`\n- Monto: {f['amount_usd']} USD ({f['amount_cup']} CUP)\n- Método: {f['method']}\n- ID: `{pid}`\n\nUsa /approve `{pid}` o /reject `{pid}` <motivo> para gestionarlo."
                )
            except Exception:
                logging.warning(f"No se pudo notificar al boss {boss_id}")
        flows.pop(user_id, None)
        return

# ---------- Pagos: Listar/Aprobar/Rechazar (Boss) ----------
@bot.on(events.NewMessage(pattern=r"^💳 Pagos$|^/payments$"))
async def list_payments(ev):
    """
    Muestra los últimos 30 pagos al administrador.
    
    Args:
        ev: Evento con el comando "Pagos" o /payments.
    """
    if role_for(ev.sender_id) != "boss":
        await reply(ev, MSG_ERROR_NO_PERMISSION)
        return
    with cx() as c:
        cur = c.cursor()
        cur.execute("SELECT * FROM payments ORDER BY created DESC LIMIT 30")
        rows = cur.fetchall()
    await reply(ev, fmt_payments_pretty(rows), kb_boss())
    logging.info(f"Lista de pagos solicitada por boss {ev.sender_id}")

@bot.on(events.NewMessage(pattern=r"^/approve\s+([a-f0-9]{10,})$"))
async def approve(ev):
    """
    Aprueba un pago pendiente y aplica los cambios correspondientes (solo boss).
    
    Args:
        ev: Evento con el comando /approve <id>.
    """
    if role_for(ev.sender_id) != "boss":
        await reply(ev, MSG_ERROR_NO_PERMISSION)
        return
    pid = ev.pattern_match.group(1)
    with cx() as c:
        cur = c.cursor()
        cur.execute("SELECT * FROM payments WHERE id=?", (pid,))
        p = cur.fetchone()
        if not p:
            await reply(ev, f"❌ **Error**: No existe el pago con ID `{pid}`.", kb_boss())
            logging.error(f"Pago no encontrado para aprobar: {pid}")
            return
        if p["status"] != "pending":
            await reply(ev, f"⚠️ **Error**: El pago `{pid}` no está pendiente.", kb_boss())
            logging.error(f"Intento de aprobar pago no pendiente: {pid}")
            return

        if p["plan"].startswith("res_") and p["role"] == "reseller":
            rid = p["item_id"]
            cur.execute("SELECT plan, started, expires FROM resellers WHERE id=?", (rid,))
            r = cur.fetchone()
            if r:
                pr = prices(cur)
                old_base = pr[r["plan"]]
                new_base = pr[p["plan"]]
                extra = prorate(old_base, new_base, r["started"], r["expires"])
                cur.execute("UPDATE resellers SET plan=? WHERE id=?", (p["plan"], rid))
                cur.execute(
                    "INSERT INTO audit(actor_id, action, meta, created) VALUES (?, ?, ?, ?)",
                    (ev.sender_id, "approve_reseller_upgrade",
                     f"rid={rid}; old={r['plan']}; new={p['plan']}; extra={extra}", iso_now())
                )
        elif p["plan"].startswith("client_"):
            slug = p["item_id"]
            days = {"client_30": 30, "client_90": 90, "client_365": 365}[p["plan"]]
            cur.execute("SELECT expires FROM clients WHERE slug=?", (slug,))
            r = cur.fetchone()
            base_date = dt.date.fromisoformat(r["expires"]) if r else dt.date.today()
            if base_date < dt.date.today():
                base_date = dt.date.today()
            new_exp = (base_date + dt.timedelta(days=days)).isoformat()
            cur.execute("UPDATE clients SET expires=? WHERE slug=?", (new_exp, slug))
            cur.execute(
                "INSERT INTO audit(actor_id, action, meta, created) VALUES (?, ?, ?, ?)",
                (ev.sender_id, "approve_client_renew", f"slug={slug}; +{days}d -> {new_exp}", iso_now())
            )
        cur.execute("UPDATE payments SET status='approved' WHERE id=?", (pid,))
        c.commit()
    await reply(ev, f"✅ **Pago aprobado**\nID: `{pid}`\nEl usuario ha sido notificado.", kb_boss())
    logging.info(f"Pago aprobado por boss {ev.sender_id}: ID={pid}")
    try:
        await bot.send_message(p["user_id"], f"✅ **¡Pago aprobado!**\nTu plan `{p['plan']}` ha sido actualizado. Gracias por tu pago.")
    except Exception:
        logging.warning(f"No se pudo notificar al usuario {p['user_id']} de aprobación")

@bot.on(events.NewMessage(pattern=r"^/reject\s+([a-f0-9]{10,})\s*(.*)$"))
async def reject(ev):
    """
    Rechaza un pago pendiente con un motivo (solo boss).
    
    Args:
        ev: Evento con el comando /reject <id> [motivo].
    """
    if role_for(ev.sender_id) != "boss":
        await reply(ev, MSG_ERROR_NO_PERMISSION)
        return
    pid = ev.pattern_match.group(1)
    reason = (ev.pattern_match.group(2) or "Sin motivo").strip()
    with cx() as c:
        cur = c.cursor()
        cur.execute("SELECT user_id, status FROM payments WHERE id=?", (pid,))
        p = cur.fetchone()
        if not p:
            await reply(ev, f"❌ **Error**: No existe el pago con ID `{pid}`.", kb_boss())
            logging.error(f"Pago no encontrado para rechazar: {pid}")
            return
        if p["status"] != "pending":
            await reply(ev, f"⚠️ **Error**: El pago `{pid}` no está pendiente.", kb_boss())
            logging.error(f"Intento de rechazar pago no pendiente: {pid}")
            return
        cur.execute("UPDATE payments SET status='rejected' WHERE id=?", (pid,))
        c.commit()
    await reply(ev, f"❌ **Pago rechazado**\nID: `{pid}`\nMotivo: {reason}", kb_boss())
    logging.info(f"Pago rechazado por boss {ev.sender_id}: ID={pid}, motivo={reason}")
    try:
        await bot.send_message(p["user_id"], f"❌ **Pago rechazado**\nID: `{pid}`\nMotivo: {reason}\nPor favor, revisa y vuelve a intentarlo.")
    except Exception:
        logging.warning(f"No se pudo notificar al usuario {p['user_id']} de rechazo")

# ---------- Vencimientos ----------
async def expiry_loop():
    """
    Verifica periódicamente los vencimientos de clientes y envía notificaciones.
    - Avisa 1 día antes del vencimiento.
    - Notifica si el plan ya venció.
    """
    while True:
        try:
            today = dt.date.today().isoformat()
            with cx() as c:
                cur = c.cursor()
                cur.execute("SELECT owner_id, slug, expires FROM clients WHERE date(expires)=date(?, '+1 day')", (today,))
                for r in cur.fetchall():
                    try:
                        await bot.send_message(r["owner_id"], MSG_EXPIRES_TOMORROW.format(slug=r["slug"], expires=r["expires"]))
                        logging.info(f"Notificación de vencimiento enviada a {r['owner_id']}: slug={r['slug']}")
                    except Exception:
                        logging.warning(f"No se pudo enviar notificación de vencimiento a {r['owner_id']}")
                cur.execute("SELECT owner_id, slug, expires FROM clients WHERE date(expires)<=date(?)", (today,))
                for r in cur.fetchall():
                    try:
                        await bot.send_message(r["owner_id"], MSG_EXPIRED.format(slug=r["slug"], expires=r["expires"]))
                        logging.info(f"Notificación de plan vencido enviada a {r['owner_id']}: slug={r['slug']}")
                    except Exception:
                        logging.warning(f"No se pudo enviar notificación de vencido a {r['owner_id']}")
        except Exception as e:
            logging.error(f"Error en expiry_loop: {e}")
        await asyncio.sleep(3600)

# ---------- Main ----------
async def main():
    """
    Inicializa la base de datos, arranca el bot y ejecuta la tarea de vencimientos.
    """
    init_db()
    await bot.start(bot_token=SET.bot_token)
    logging.info("✅ Bot de resellers iniciado correctamente.")
    print("✅ Bot de resellers iniciado correctamente.")
    asyncio.create_task(expiry_loop())
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
