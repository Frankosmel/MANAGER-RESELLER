from telethon import Button, types

# ---------- Reply Keyboards ----------
def _b(t: str): return types.KeyboardButton(text=t)
def _row(*texts): return types.KeyboardButtonRow(buttons=[_b(t) for t in texts])

def kb_boss():
    return types.ReplyKeyboardMarkup(
        rows=[_row("💼 Resellers","👥 Clientes"),
              _row("💳 Pagos","🧾 Facturas"),
              _row("⚙️ Ajustes")],
        resize=True
    )

def kb_reseller():
    return types.ReplyKeyboardMarkup(
        rows=[_row("👥 Mis clientes","➕ Crear cliente"),
              _row("💳 Pagar / Renovar","📞 Soporte Boss")],
        resize=True
    )

def kb_client():
    return types.ReplyKeyboardMarkup(
        rows=[_row("📄 Mi plan","⚙️ Provisionar"),
              _row("💳 Pagar / Renovar","📞 Soporte")],
        resize=True
    )

# ---------- Inline Blocks ----------
def inline_plans_reseller(prices, rate):
    text = (
        "🏷 **Planes Reseller (USD / CUP)**\n"
        f"• Básico: {prices['res_b']} / {int(prices['res_b']*rate)}\n"
        f"• Pro: {prices['res_p']} / {int(prices['res_p']*rate)}\n"
        f"• Enterprise: {prices['res_e']} / {int(prices['res_e']*rate)}"
    )
    btn = [
        [Button.inline("Básico", b"pay:res_b"),
         Button.inline("Pro", b"pay:res_p"),
         Button.inline("Enterprise", b"pay:res_e")],
        [Button.inline("« Atrás", b"pay:back")]
    ]
    return text, btn

def inline_pay_methods(usd, cup):
    txt = f"💰 **Monto:** {usd} USD (**{cup} CUP**)\n\nElige método de pago:"
    btn = [[Button.inline("Saldo", b"pay:m:saldo"), Button.inline("CUP", b"pay:m:cup")],
           [Button.inline("« Atrás", b"pay:plan")]]
    return txt, btn

def inline_client_terms(p):
    txt = (
        "🗓 **Renovar cliente**\n"
        f"• 30 días: {p['c30']} USD\n"
        f"• 90 días: {p['c90']} USD\n"
        f"• 365 días: {p['c365']} USD"
    )
    btn = [[Button.inline("30 días", b"pay:c:30"),
            Button.inline("90 días", b"pay:c:90"),
            Button.inline("365 días", b"pay:c:365")],
           [Button.inline("« Atrás", b"pay:back")]]
    return txt, btn

def inline_pick_client(slugs):
    rows, row = [], []
    for s in slugs:
        row.append(Button.inline(f"👤 {s}", f"pay:cli:{s}".encode()))
        if len(row) == 2:
            rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([Button.inline("« Atrás", b"pay:back")])
    return rows

def btn_send_receipt():
    return [[Button.inline("📤 Enviar comprobante", b"pay:receipt")],
            [Button.inline("« Atrás", b"pay:back")]]

# ---------- Pretty Formatters ----------
STATE_ICON = {"active":"🟢 Activo","stopped":"🔴 Pausado","unknown":"⚪ Desconocido"}
STATUS_ICON = {"pending":"⏳ Pendiente","approved":"✅ Aprobado","rejected":"❌ Rechazado"}
def _fmt_money_cup(x): return f"{int(x):,} CUP".replace(",", " ")

def fmt_payments_pretty(rows):
    if not rows: return "🧾 PAGOS RECIENTES\n\nNo hay registros."
    out=["🧾 PAGOS RECIENTES\n"]
    for r in rows:
        out += [
            f"🔸 ID: {r['id']}",
            f"   📌 Estado: {STATUS_ICON.get(r['status'], r['status'])}",
            f"   💵 Monto: {r['amount_usd']} USD",
            f"   💱 Equivalente: {_fmt_money_cup(r['amount_cup'])}",
            f"   👤 Plan/Concepto: {r['plan']}",
            f"   🛒 Item: {r['item_id']}",
            f"   🆔 Usuario: {r['user_id']}",
            ""
        ]
    out.append("⚙️ Comandos:\n/approve <id>\n/reject <id> <motivo>")
    return "\n".join(out)

def fmt_resellers_list(rows):
    if not rows: return "💼 RESELLERS\n\nNo hay resellers."
    out=["💼 RESELLERS\n"]
    for r in rows:
        out.append(f"🔹 {r['id']} • {r['plan']} • vence {r['expires']} • {r.get('contact','N/A')} • 👥 {r.get('clients',0)}")
    return "\n".join(out)

def fmt_clients_list(rows, title="👥 CLIENTES"):
    if not rows: return f"{title}\n\nNo hay clientes."
    out=[f"{title}\n"]
    for c in rows:
        out.append(f"🔹 {c['slug']} • {c['plan']} • vence {c['expires']} • reseller {c['reseller_id']}")
    return "\n".join(out)

def fmt_client_card(c):
    return (
        "👤 **CLIENTE**\n\n"
        f"🧭 Slug: `{c['slug']}`\n"
        f"🆔 Owner: {c['owner_id']} (@{c.get('username','N/A')})\n"
        f"💼 Reseller: {c['reseller_id']}\n"
        f"🏷 Plan: {c['plan']}\n"
        f"📅 Vence: {c['expires']}\n"
        f"🗂 Workdir: `{c['workdir']}`\n"
        f"🛰 Servicio: {STATE_ICON.get(c.get('svc_status','unknown'),'')}"
    )

def fmt_status_panel(s):
    return (
        "📊 **ESTADO DEL SERVICIO**\n\n"
        f"🏷 Plan: {s['plan']}\n"
        f"🧭 Slug: `{s['slug']}`\n"
        f"📅 Vence: {s['expires']}\n"
        f"🛰 Servicio: {STATE_ICON.get(s['svc'],'')}\n"
        f"🤖 Bot: @{s.get('bot','No configurado')}\n"
        f"📁 Dir: `{s['workdir']}`"
    )

# ---------- Messages ----------
MSG_CLIENT_WELCOME = (
    "🚀 **Tu Panel de Servicio**\n\n"
    "🔖 Plan: **{plan}**\n"
    "📅 Vence: **{expires}**\n"
    "🧭 ID: `{slug}`\n\n"
    "💡 Renueva a tiempo desde **💳 Pagar / Renovar**."
)
MSG_RES_LIMIT = "⛔ **Límite alcanzado** ({limit} bots). Sube de plan para seguir creciendo 📈."
MSG_PAY_PICK = "💳 **¿Qué deseas pagar?**\n• Plan Reseller (Básico/Pro/Enterprise)\n• Renovar cliente (30/90/365)"
MSG_PAY_SALDO = "{txt}\n\nLuego pulsa **📤 Enviar comprobante** y sube la captura."
MSG_PAY_CUP = "{txt}\n\nLuego pulsa **📤 Enviar comprobante** y sube la captura."
MSG_RECEIPT_OK = "✅ **Comprobante recibido**. El Boss revisará y aprobará."
MSG_EXPIRES_TMR = "⚠️ **Tu servicio '{slug}' vence mañana.** Renueva con **💳 Pagar / Renovar**."
MSG_EXPIRED = "🔴 **Tu servicio '{slug}' ha sido pausado por vencimiento**."
MSG_CREATED_CLIENT = "✅ Cliente `{slug}` creado para reseller `{rid}`. ¡A volar! ✈️"
MSG_CREATED_RESELLER = "✅ Reseller `{rid}` activado en plan **Básico**. ¡A vender! 🏁"
