# app/ui.py
from telethon import Button

# ===== Reply keyboards por rol =====
def kb_boss():
    return Button.keyboard([
        [Button.text("💼 Resellers"), Button.text("👥 Clientes")],
        [Button.text("💳 Pagos"), Button.text("🧾 Facturas")],
        [Button.text("⚙️ Ajustes")]
    ], resize=True)

def kb_reseller():
    return Button.keyboard([
        [Button.text("👥 Mis clientes"), Button.text("➕ Crear cliente")],
        [Button.text("💳 Pagar / Renovar"), Button.text("📞 Soporte Boss")]
    ], resize=True)

def kb_client():
    return Button.keyboard([
        [Button.text("📄 Mi plan"), Button.text("⚙️ Provisionar")],
        [Button.text("💳 Pagar / Renovar"), Button.text("📞 Soporte")]
    ], resize=True)

# ===== Bloques inline =====
def inline_plans_reseller(prices, rate):
    return (
        f"🏷 **Planes Reseller (USD / CUP)**\n"
        f"• Básico: {prices['res_b']} / {int(prices['res_b']*rate)}\n"
        f"• Pro: {prices['res_p']} / {int(prices['res_p']*rate)}\n"
        f"• Enterprise: {prices['res_e']} / {int(prices['res_e']*rate)}"
    ), [
        [Button.inline("Básico", b"pay:res_b"), Button.inline("Pro", b"pay:res_p"), Button.inline("Enterprise", b"pay:res_e")],
        [Button.inline("« Atrás", b"pay:back")]
    ]

def inline_pay_methods(usd, cup):
    txt = f"💰 **Monto:** {usd} USD (**{cup} CUP**)\n\nElige método de pago:"
    btn = [[Button.inline("Saldo", b"pay:m:saldo"), Button.inline("CUP", b"pay:m:cup")],
           [Button.inline("« Atrás", b"pay:plan")]]
    return txt, btn

def inline_client_terms(p):
    txt = (
        f"🗓 **Renovar cliente**\n"
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
        if len(row) == 2: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([Button.inline("« Atrás", b"pay:back")])
    return rows

def btn_send_receipt():
    return [[Button.inline("📤 Enviar comprobante", b"pay:receipt")],
            [Button.inline("« Atrás", b"pay:back")]]

# ===== Menajes amigables =====
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
MSG_EXPIRED = "🔴 **Tu servicio '{slug}' ha sido pausado por vencimiento.**"
MSG_CREATED_CLIENT = "✅ Cliente `{slug}` creado para reseller `{rid}`. ¡A volar! ✈️"
MSG_CREATED_RESELLER = "✅ Reseller `{rid}` activado en plan **Básico**. ¡A vender! 🏁"
