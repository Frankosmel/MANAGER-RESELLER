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
    inline_plans_reseller, inline_pay_methods, inline_client_terms, inline_pick_client, btn_send_receipt
)

# Inicializar cliente de Telegram
bot = TelegramClient("reseller_mgr", SET.api_id, SET.api_hash)
flows = {}  # Diccionario para almacenar el estado de conversación por usuario

# Mensajes explicativos y profesionales para todos los roles
MSG_WELCOME_GUEST = (
    "👋 **¡Bienvenido(a)!**\n"
    "Aún no estás registrado en el sistema. Para comenzar, contacta a tu reseller o escribe a nuestro soporte en @{support_contact}.\n"
    "¡Estamos aquí para ayudarte!"
)
MSG_WELCOME_BOSS = (
    "👑 **Panel de Administrador**\n"
    "¡Bienvenido, jefe! Tienes control total del sistema. Desde aquí puedes:\n"
    "- Crear y gestionar resellers.\n"
    "- Configurar precios y tasas.\n"
    "- Aprobar o rechazar pagos.\n\n"
    "Selecciona una opción para continuar:"
)
MSG_WELCOME_RESELLER = (
    "💼 **Panel de Reseller**\n"
    "¡Hola! Eres un reseller y puedes:\n"
    "- Crear y administrar clientes.\n"
    "- Renovar planes de clientes.\n"
    "- Consultar tu lista de clientes.\n\n"
    "Elige una acción para empezar:"
)
MSG_WELCOME_CLIENT = (
    "👤 **Hola, {username}!**\n"
    "Tu cuenta está activa. Aquí están los detalles de tu plan:\n"
    "- **Plan**: {plan}\n"
    "- **Vence**: {expires}\n"
    "- **Slug**: `{slug}`\n\n"
    "Usa los botones para renovar tu plan o contactar a tu reseller para soporte."
)
MSG_ERROR_NO_PERMISSION = (
    "🔒 **Acceso denegado**\n"
    "No tienes permisos para realizar esta acción. Verifica tu rol o contacta a soporte."
)
MSG_ERROR_INVALID_ID = (
    "❌ **ID inválido**\n"
    "El ID debe ser un número válido (por ejemplo, 123456789). Por favor, intenta de nuevo."
)
MSG_CLIENT_CREATED = (
    "🎉 **Cliente creado exitosamente**\n"
    "- **Slug**: `{slug}`\n"
    "- **Reseller ID**: `{rid}`\n"
    "- **Plan**: plan_estandar\n"
    "- **Vence**: `{expires}`\n\n"
    "El cliente ya puede usar el servicio. Notifícalo con su slug."
)
MSG_RESELLER_CREATED = (
    "🎉 **Reseller creado**\n"
    "- **ID**: `{rid}`\n"
    "- **Plan**: {plan}\n"
    "- **Vence**: `{expires}`\n\n"
    "El reseller ha sido registrado y puede comenzar a crear clientes."
)
MSG_PAYMENT_PICK = (
    "💳 **Realizar un pago**\n"
    "Selecciona qué quieres pagar o renovar:\n"
    "- **Plan Reseller**: Actualiza o renueva tu plan de reseller.\n"
    "- **Renovar Cliente**: Extiende el plan de un cliente existente."
)
MSG_PAYMENT_SALDO = (
    "💵 **Pagar con saldo**\n"
    "{txt}\n"
    "Monto a pagar: **{monto_saldo} CUP**\n\n"
    "Por favor, adjunta el comprobante de pago en el chat."
)
MSG_PAYMENT_CUP = (
    "💵 **Pagar en CUP**\n"
    "{txt}\n"
    "Monto a pagar: **{monto_cup} CUP**\n\n"
    "Por favor, adjunta el comprobante de pago en el chat."
)
MSG_PAYMENT_SUCCESS = (
    "✅ **Pago registrado**\n"
    "- **ID de transacción**: `{pid}`\n"
    "- **Monto**: {amount_usd} USD ({amount_cup} CUP)\n"
    "- **Método**: {method}\n"
    "- **Plan**: {plan}\n\n"
    "Tu pago está en revisión. Te notificaremos cuando sea aprobado."
)
MSG_EXPIRES_TOMORROW = (
    "⚠️ **Recordatorio de vencimiento**\n"
    "Tu plan `{slug}` vence **mañana** ({expires}).\n"
    "Renueva ahora para evitar interrupciones en el servicio."
)
MSG_EXPIRED = (
    "❌ **Plan vencido**\n"
    "Tu plan `{slug}` ha expirado ({expires}).\n"
    "Por favor, renueva tu plan para continuar usando el servicio."
)
MSG_RES_LIMIT = (
    "🚫 **Límite alcanzado**\n"
    "Tu plan de reseller permite un máximo de {limit} clientes.\n"
    "Actualiza tu plan para crear más clientes."
)

# Función auxiliar para enviar mensajes formateados
async def reply(ev, message, buttons=None, parse_mode="markdown"):
    """
    Enviar un mensaje con formato Markdown y botones opcionales.
    
    Args:
        ev: Evento de Telegram (mensaje o callback).
        message: Mensaje a enviar.
        buttons: Botones opcionales (ReplyKeyboard o InlineKeyboard).
        parse_mode: Formato del mensaje (por defecto, Markdown).
    """
    await ev.reply(message, buttons=buttons or Button.clear(), parse_mode=parse_mode)

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
            await reply(ev, "👤 **Cliente registrado**\nNo se encontraron detalles de tu plan. Contacta a soporte.", kb_client())
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
        await bot.get_entity(int(new_owner_id))  # Verificar si el ID existe en Telegram
    except ValueError:
        await reply(ev, "❌ **Error**: El ID de usuario no es válido. Debe ser un ID numérico existente.")
        return
    set_setting("owner_id", new_owner_id)
    await reply(ev, f"👑 **Dueño establecido**\nID: `{new_owner_id}`\nEl sistema está ahora bajo tu control.")

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
        await bot.get_entity(int(rid))  # Verificar si el ID existe
    except ValueError:
        await reply(ev, "❌ **Error**: El ID del reseller no es válido. Debe ser un ID numérico existente.")
        return
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

# ---------- Boss: Actualizar Contacto de Reseller ----------
@bot.on(events.NewMessage(pattern=r"^/reseller_contact\s+(\d+)\s+(@?\S+)$"))
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
        return
    with cx() as c:
        cur = c.cursor()
        cur.execute("SELECT 1 FROM resellers WHERE id=?", (rid,))
        if not cur.fetchone():
            await reply(ev, f"❌ **Error**: No existe un reseller con ID `{rid}`.")
            return
        cur.execute("UPDATE resellers SET contact=? WHERE id=?", (tag, rid))
        c.commit()
    await reply(ev, f"📞 **Contacto actualizado**\nReseller `{rid}` ahora tiene contacto: `{tag}`.", kb_boss())

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
    rate = ev.pattern_match.group(1)
    set_setting("usd_to_cup", rate)
    await reply(ev, f"💱 **Tasa actualizada**\nNueva tasa USD→CUP: `{rate}`.", kb_boss())

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
    val = ev.pattern_match.group(2)
    mapk = {
        "res_b": "price_res_b", "res_p": "price_res_p", "res_e": "price_res_e",
        "c30": "price_client_30", "c90": "price_client_90", "c365": "price_client_365"
    }[key]
    set_setting(mapk, val)
    await reply(ev, f"💵 **Precio actualizado**\nPlan `{key}` establecido en `{val}` USD.", kb_boss())

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
        cur.execute("SELECT id, plan, expires, contact FROM resellers ORDER BY id")
        rows = cur.fetchall()
    if not rows:
        await reply(ev, "📭 **Sin resellers**\nNo hay resellers registrados. Crea uno con /reseller_add.", kb_boss())
        return
    lines = ["💼 **Lista de Resellers**"]
    lines += [f"- ID: `{x['id']}` | Plan: `{x['plan']}` | Vence: `{x['expires']}` | Contacto: `{x['contact']}`" 
              for x in rows]
    await reply(ev, "\n".join(lines), kb_boss())

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
        cur.execute("SELECT slug, expires FROM clients WHERE reseller_id=?", (str(ev.sender_id),))
        rows = cur.fetchall()
    if not rows:
        await reply(ev, "📭 **Sin clientes**\nNo tienes clientes registrados. Usa 'Crear cliente' para agregar uno.", kb_reseller())
        return
    lines = ["👥 **Tus Clientes**"]
    lines += [f"- Slug: `{x['slug']}` | Vence: `{x['expires']}`" for x in rows]
    await reply(ev, "\n".join(lines), kb_reseller())

@bot.on(events.NewMessage(pattern=r"^➕ Crear cliente$"))
async def res_create(ev):
    """
    Inicia el proceso de creación de un cliente para un reseller.
    
    Args:
        ev: Evento con el comando "Crear cliente".
    """
    if role_for(ev.sender_id) != "reseller":
        await reply(ev, MSG_ERROR_NO_PERMISSION)
        return
    flows[ev.sender_id] = {"mode": "newcli", "step": "client_id", "rid": str(ev.sender_id)}
    await reply(ev, "🆕 **Crear Cliente**\nEnvía el **ID numérico** del cliente (ej. 123456789):", kb_reseller())

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

@bot.on(events.NewMessage(pattern=r"^📞 Soporte$"))
async def cli_support(ev):
    """
    Muestra el contacto del reseller al cliente o boss.
    
    Args:
        ev: Evento con el comando "Soporte".
    """
    role = role_for(ev.sender_id)
    if role not in ("client", "boss", "reseller"):
        await reply(ev, MSG_ERROR_NO_PERMISSION)
        return
    with cx() as c:
        cur = c.cursor()
        cur.execute("SELECT reseller_id FROM clients WHERE owner_id=?", (ev.sender_id,))
        row = cur.fetchone()
        if not row:
            await reply(ev, "❌ **Error**: No estás registrado como cliente.", kb_client())
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

# ---------- Flujos Inline (Pagos) ----------
@bot.on(events.CallbackQuery)
async def cb(ev):
    """
    Maneja las interacciones con botones inline en el flujo de pagos.
    
    Args:
        ev: Evento de CallbackQuery con datos de la acción seleccionada.
    """
    user_id = ev.sender_id
    role = role_for(user_id)
    data = (ev.data or b"").decode()

    # Seleccionar plan de reseller
    if data == "pay:plan" and user_id in flows and flows[user_id]["mode"] == "pay":
        with cx() as c:
            cur = c.cursor()
            pr = prices(cur)
            rate = pr["usd_to_cup"]
        txt, btn = inline_plans_reseller(pr, rate)
        await ev.edit(txt, buttons=btn)
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
        flows[user_id] |= {"step": "pay_method", "plan_code": code, "amount_usd": usd, "amount_cup": cup, "item_id": str(user_id)}
        txt, btn = inline_pay_methods(usd, cup)
        await ev.edit(txt, buttons=btn)
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
                return
            flows[user_id]["client_slug"] = row["slug"]
        else:
            with cx() as c:
                cur = c.cursor()
                cur.execute("SELECT slug FROM clients WHERE reseller_id=?", (str(user_id),))
                slugs = [x["slug"] for x in cur.fetchall()]
            if not slugs:
                await ev.answer("📭 No tienes clientes registrados.", alert=True)
                return
            await ev.edit("👥 **Elige un cliente para renovar**:", buttons=inline_pick_client(slugs))
            return
        # Mostrar términos del cliente
        with cx() as c:
            cur = c.cursor()
            pr = prices(cur)
        txt, btn = inline_client_terms(pr)
        await ev.edit(txt, buttons=btn)
        return

    # Reseller elige cliente
    if data.startswith("pay:cli:") and user_id in flows and flows[user_id]["mode"] == "pay":
        flows[user_id]["client_slug"] = data.split(":", 2)[2]
        with cx() as c:
            cur = c.cursor()
            pr = prices(cur)
        txt, btn = inline_client_terms(pr)
        await ev.edit(txt, buttons=btn)
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
        flows[user_id] |= {
            "step": "pay_method",
            "plan_code": f"client_{term}",
            "amount_usd": usd,
            "amount_cup": cup,
            "item_id": flows[user_id].get("client_slug")
        }
        txt, btn = inline_pay_methods(usd, cup)
        await ev.edit(txt, buttons=btn)
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
        return

    # Subir comprobante
    if data == "pay:receipt" and user_id in flows and flows[user_id]["mode"] == "pay":
        flows[user_id]["await_receipt"] = True
        await ev.answer("📎 Por favor, adjunta la imagen del comprobante en el chat.", alert=True)
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
            return
        with cx() as c:
            cur = c.cursor()
            cur.execute("SELECT plan, started, expires FROM resellers WHERE id=?", (f["rid"],))
            reseller = cur.fetchone()
            if not reseller:
                await reply(ev, "❌ **Error**: No eres un reseller válido.", kb_reseller())
                flows.pop(user_id, None)
                return
            # Verificar límites de clientes
            lims = limits(cur)
            lim = lims.get(reseller["plan"], 0)
            cur.execute("SELECT COUNT(*) AS n FROM clients WHERE reseller_id=?", (f["rid"],))
            used = cur.fetchone()["n"]
            if lim and used >= lim:
                await reply(ev, MSG_RES_LIMIT.format(limit=lim), kb_reseller())
                flows.pop(user_id, None)
                return
            # Generar slug único
            slug = slugify(str(cid))
            base = slug
            i = 2
            while True:
                cur.execute("SELECT 1 FROM clients WHERE slug=?", (slug,))
                if not cur.fetchone():
                    break
                slug = f"{base}{i}"
                i += 1
            # Crear cliente
            wdir = ensure_client_workdir(slug)
            expires = (dt.date.today() + dt.timedelta(days=30)).isoformat()
            cur.execute(
                """INSERT INTO clients(slug, owner_id, username, reseller_id, plan, expires, created, workdir, svc_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (slug, cid, None, f["rid"], "plan_estandar", expires, iso_now(), str(wdir), "stopped")
            )
            c.commit()
        flows.pop(user_id, None)
        await reply(ev, MSG_CLIENT_CREATED.format(slug=slug, rid=f["rid"], expires=expires), kb_reseller())
        # Notificar al cliente
        try:
            await bot.send_message(cid, f"🎉 **¡Bienvenido!**\nHas sido registrado como cliente.\nTu slug es `{slug}` y tu plan vence el `{expires}`.\nUsa /start para más detalles.")
        except Exception:
            pass
        return

    # Recepción de comprobante de pago
    if f.get("mode") == "pay" and f.get("await_receipt"):
        if not (ev.photo or ev.document):
            await reply(ev, "📎 **Error**: Por favor, adjunta una imagen del comprobante.")
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
        flows.pop(user_id, None)
        await reply(ev, MSG_PAYMENT_SUCCESS.format(
            pid=pid, amount_usd=f["amount_usd"], amount_cup=f["amount_cup"], method=f["method"], plan=f["plan_code"]
        ))
        # Notificar al boss
        boss_id = int(get_setting("owner_id", "0") or 0)
        if boss_id:
            try:
                await bot.send_message(
                    boss_id,
                    f"🧾 **Nuevo pago pendiente**\n- Usuario: `{user_id}`\n- Monto: {f['amount_usd']} USD ({f['amount_cup']} CUP)\n- Método: {f['method']}\n- ID: `{pid}`\n\nUsa /approve `{pid}` o /reject `{pid}` <motivo> para gestionarlo."
                )
            except Exception:
                pass
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
        cur.execute("SELECT id, user_id, role, type, amount_usd, amount_cup, status, plan, item_id, created FROM payments ORDER BY created DESC LIMIT 30")
        rows = cur.fetchall()
    if not rows:
        await reply(ev, "📭 **Sin pagos**\nNo hay pagos registrados.", kb_boss())
        return
    lines = ["🧾 **Pagos Recientes**"]
    lines += [
        f"- ID: `{r['id']}` | Estado: `{r['status']}` | {r['amount_usd']} USD ({r['amount_cup']} CUP) | {r['role']}/{r['type']} | Plan: `{r['plan']}` | Item: `{r['item_id']}` | Usuario: `{r['user_id']}`"
        for r in rows
    ]
    lines.append("\n**Gestiona pagos**:\n- Aprobar: `/approve <id>`\n- Rechazar: `/reject <id> <motivo>`")
    await reply(ev, "\n".join(lines), kb_boss())

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
            return
        if p["status"] != "pending":
            await reply(ev, f"⚠️ **Error**: El pago `{pid}` no está pendiente.", kb_boss())
            return

        # Aplicar efecto del pago
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
        # Marcar pago como aprobado
        cur.execute("UPDATE payments SET status='approved' WHERE id=?", (pid,))
        c.commit()

    await reply(ev, f"✅ **Pago aprobado**\nID: `{pid}`\nEl usuario ha sido notificado.", kb_boss())
    try:
        await bot.send_message(p["user_id"], f"✅ **¡Pago aprobado!**\nTu plan `{p['plan']}` ha sido actualizado. Gracias por tu pago.")
    except Exception:
        pass

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
            return
        if p["status"] != "pending":
            await reply(ev, f"⚠️ **Error**: El pago `{pid}` no está pendiente.", kb_boss())
            return
        cur.execute("UPDATE payments SET status='rejected' WHERE id=?", (pid,))
        c.commit()
    await reply(ev, f"❌ **Pago rechazado**\nID: `{pid}`\nMotivo: {reason}", kb_boss())
    try:
        await bot.send_message(p["user_id"], f"❌ **Pago rechazado**\nID: `{pid}`\nMotivo: {reason}\nPor favor, revisa y vuelve a intentarlo.")
    except Exception:
        pass

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
                # Avisar 1 día antes
                cur.execute("SELECT owner_id, slug, expires FROM clients WHERE date(expires)=date(?, '+1 day')", (today,))
                for r in cur.fetchall():
                    try:
                        await bot.send_message(r["owner_id"], MSG_EXPIRES_TOMORROW.format(slug=r["slug"], expires=r["expires"]))
                    except Exception:
                        pass
                # Notificar vencidos
                cur.execute("SELECT owner_id, slug, expires FROM clients WHERE date(expires)<=date(?)", (today,))
                for r in cur.fetchall():
                    try:
                        await bot.send_message(r["owner_id"], MSG_EXPIRED.format(slug=r["slug"], expires=r["expires"]))
                    except Exception:
                        pass
        except Exception as e:
            print(f"Error en expiry_loop: {e}")
        await asyncio.sleep(3600)  # Revisar cada hora

# ---------- Main ----------
async def main():
    """
    Inicializa la base de datos, arranca el bot y ejecuta la tarea de vencimientos.
    """
    init_db()
    await bot.start(bot_token=SET.bot_token)
    print("✅ Bot de resellers iniciado correctamente.")
    asyncio.create_task(expiry_loop())
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
