# app/bot.py
import asyncio, datetime as dt
from telethon import TelegramClient, events, Button
from .config import SET
from .models_db import (
    init_db, cx, get_setting, set_setting, role_for, limits, prices,
    prorate, ensure_client_workdir, slugify, new_id, iso_now
)
from .ui import (
    kb_boss, kb_reseller, kb_client,
    inline_plans_reseller, inline_pay_methods, inline_client_terms, inline_pick_client, btn_send_receipt,
    MSG_CLIENT_WELCOME, MSG_RES_LIMIT, MSG_PAY_PICK, MSG_PAY_SALDO, MSG_PAY_CUP,
    MSG_RECEIPT_OK, MSG_EXPIRES_TMR, MSG_EXPIRED, MSG_CREATED_CLIENT, MSG_CREATED_RESELLER
)

bot = TelegramClient("reseller_mgr", SET.api_id, SET.api_hash)
flows = {}  # estado de conversación por usuario

# ---------- /start ----------
@bot.on(events.NewMessage(pattern=r"^/start$"))
async def start(ev):
    init_db()
    r = role_for(ev.sender_id)
    if r == "guest":
        await ev.reply("🔒 Acceso restringido. Pide alta a tu reseller.", buttons=Button.clear()); return
    if r == "boss":
        await ev.reply("👑 **Panel Boss**\nGestiona todo el sistema.", buttons=kb_boss()); return
    if r == "reseller":
        await ev.reply("💼 **Panel Reseller**\nCrea y administra tus clientes.", buttons=kb_reseller()); return
    if r == "client":
        with cx() as c:
            cur=c.cursor()
            cur.execute("SELECT slug,plan,expires FROM clients WHERE owner_id=?", (ev.sender_id,))
            row=cur.fetchone()
        if row:
            await ev.reply(MSG_CLIENT_WELCOME.format(plan=row["plan"], expires=row["expires"], slug=row["slug"]),
                           buttons=kb_client()); return
        await ev.reply("👤 **Cliente**", buttons=kb_client())

# ---------- Bootstrap Owner ----------
@bot.on(events.NewMessage(pattern=r"^/set_owner\s+(\d+)$"))
async def set_owner(ev):
    current = int(get_setting("owner_id", "0") or 0)
    if current not in (0, ev.sender_id): return
    set_setting("owner_id", ev.pattern_match.group(1))
    await ev.reply("👑 **Owner establecido**. Todo bajo control.")

# ---------- Boss: crear reseller ----------
@bot.on(events.NewMessage(pattern=r"^/reseller_add\s+(\d+)$"))
async def reseller_add(ev):
    if role_for(ev.sender_id) != "boss": return
    rid = ev.pattern_match.group(1)
    today = dt.date.today().isoformat()
    with cx() as c:
        cur=c.cursor()
        cur.execute("""INSERT OR REPLACE INTO resellers(id,plan,started,expires,contact)
                       VALUES(?,?,?,?,?)""",
                    (rid, "res_b", today, (dt.date.today()+dt.timedelta(days=30)).isoformat(), "@contacto"))
        c.commit()
    await ev.reply(MSG_CREATED_RESELLER.format(rid=rid), buttons=kb_boss())

# ---------- Boss: editar contacto del reseller ----------
@bot.on(events.NewMessage(pattern=r"^/reseller_contact\s+(\d+)\s+(@?\S+)$"))
async def reseller_contact(ev):
    if role_for(ev.sender_id)!="boss": return
    rid = ev.pattern_match.group(1)
    tag = ev.pattern_match.group(2)
    with cx() as c:
        cur=c.cursor()
        cur.execute("UPDATE resellers SET contact=? WHERE id=?", (tag, rid))
        c.commit()
    await ev.reply(f"📞 Contacto de reseller `{rid}` actualizado a {tag}.", buttons=kb_boss())

# ---------- Ajustes rápidos (tasas y precios) ----------
@bot.on(events.NewMessage(pattern=r"^/set_rate\s+(\d+(\.\d+)?)$"))
async def set_rate(ev):
    if role_for(ev.sender_id)!="boss": return
    rate = ev.pattern_match.group(1)
    set_setting("usd_to_cup", rate)
    await ev.reply(f"💱 Tasa USD→CUP actualizada a {rate}.", buttons=kb_boss())

@bot.on(events.NewMessage(pattern=r"^/set_price\s+(res_b|res_p|res_e|c30|c90|c365)\s+(\d+(\.\d+)?)$"))
async def set_price(ev):
    if role_for(ev.sender_id)!="boss": return
    key = ev.pattern_match.group(1); val = ev.pattern_match.group(2)
    mapk = {"res_b":"price_res_b","res_p":"price_res_p","res_e":"price_res_e",
            "c30":"price_client_30","c90":"price_client_90","c365":"price_client_365"}[key]
    set_setting(mapk, val)
    await ev.reply(f"💵 Precio `{key}` actualizado a {val} USD.", buttons=kb_boss())

# ---------- Reply Keyboard: vistas ----------
@bot.on(events.NewMessage(pattern=r"^💼 Resellers$"))
async def boss_resellers(ev):
    if role_for(ev.sender_id)!="boss": return
    with cx() as c:
        cur=c.cursor(); cur.execute("SELECT id,plan,expires,contact FROM resellers ORDER BY id")
        rows=cur.fetchall()
    if not rows:
        await ev.reply("📭 No hay resellers aún.", buttons=kb_boss()); return
    lines=["💼 **Resellers**"]+[f"• {x['id']} – {x['plan']} – vence {x['expires']} – {x['contact']}" for x in rows]
    await ev.reply("\n".join(lines), buttons=kb_boss())

@bot.on(events.NewMessage(pattern=r"^👥 Mis clientes$"))
async def res_my_clients(ev):
    if role_for(ev.sender_id)!="reseller": return
    with cx() as c:
        cur=c.cursor()
        cur.execute("SELECT slug,expires FROM clients WHERE reseller_id=?", (str(ev.sender_id),))
        rows=cur.fetchall()
    if not rows:
        await ev.reply("📭 Aún no tienes clientes.", buttons=kb_reseller()); return
    lines=["👥 **Tus clientes**"]+[f"• `{x['slug']}` → vence {x['expires']}" for x in rows]
    await ev.reply("\n".join(lines), buttons=kb_reseller())

@bot.on(events.NewMessage(pattern=r"^➕ Crear cliente$"))
async def res_create(ev):
    if role_for(ev.sender_id)!="reseller": return
    flows[ev.sender_id]={"mode":"newcli","step":"client_id","rid":str(ev.sender_id)}
    await ev.reply("🆕 Envíame el **ID numérico** del cliente final:", buttons=kb_reseller())

@bot.on(events.NewMessage(pattern=r"^📞 Soporte Boss$"))
async def res_support_boss(ev):
    if role_for(ev.sender_id)!="reseller": return
    boss = get_setting("owner_id","")
    tag = f"@{boss}" if boss and boss.isdigit() else "N/D"
    await ev.reply(f"📞 **Contacto Boss:** {tag}", buttons=kb_reseller())

@bot.on(events.NewMessage(pattern=r"^📞 Soporte$"))
async def cli_support(ev):
    r=role_for(ev.sender_id)
    if r not in ("client","boss","reseller"): return
    with cx() as c:
        cur=c.cursor()
        cur.execute("SELECT reseller_id FROM clients WHERE owner_id=?", (ev.sender_id,))
        row=cur.fetchone()
        if not row: await ev.reply("No registrado.", buttons=kb_client()); return
        rid=row["reseller_id"]
        cur.execute("SELECT contact FROM resellers WHERE id=?", (rid,))
        rr=cur.fetchone(); contact = rr["contact"] if rr else ""
    link = f"https://t.me/{contact.lstrip('@')}" if contact else None
    if link:
        await ev.reply(f"📞 Tu reseller: {contact}", buttons=[[Button.url("💬 Abrir chat", link)]])
    else:
        await ev.reply("📞 Tu reseller: N/D", buttons=kb_client())

# ---------- Entrada de pagos ----------
@bot.on(events.NewMessage(pattern=r"^💳 Pagar / Renovar$"))
async def pay_entry(ev):
    r=role_for(ev.sender_id)
    if r not in ("client","reseller"): return
    flows[ev.sender_id]={"mode":"pay","step":"target","as":("reseller" if r=="reseller" else "client")}
    await ev.reply(MSG_PAY_PICK, buttons=[
        [Button.inline("Plan Reseller", b"pay:plan"), Button.inline("Renovar Cliente", b"pay:client")],
    ])

# ---------- Inline flows de pago ----------
@bot.on(events.CallbackQuery)
async def cb(ev):
    uid = ev.sender_id
    r = role_for(uid)
    data = (ev.data or b"").decode()

    # elegir plan reseller
    if data == "pay:plan" and uid in flows and flows[uid]["mode"]=="pay":
        with cx() as c:
            cur=c.cursor(); pr=prices(cur); rate=pr["usd_to_cup"]
        txt, btn = inline_plans_reseller(pr, rate)
        await ev.edit(txt, buttons=btn); return

    # seleccionar plan reseller concreto
    if data.startswith("pay:res_") and uid in flows and flows[uid]["mode"]=="pay":
        code = data.split(":",1)[1]
        with cx() as c:
            cur=c.cursor(); pr=prices(cur); rate=pr["usd_to_cup"]
            usd = {"res_b":pr["res_b"], "res_p":pr["res_p"], "res_e":pr["res_e"]}[code]
            cup = int(usd*rate)
        flows[uid] |= {"step":"pay_method","plan_code":code,"amount_usd":usd,"amount_cup":cup,"item_id":str(uid)}
        txt, btn = inline_pay_methods(usd, cup)
        await ev.edit(txt, buttons=btn); return

    # renovar cliente: escoger cliente
    if data == "pay:client" and uid in flows and flows[uid]["mode"]=="pay":
        # si es cliente: su propio slug; si es reseller: lista
        if r=="client":
            with cx() as c:
                cur=c.cursor()
                cur.execute("SELECT slug FROM clients WHERE owner_id=?", (uid,))
                row=cur.fetchone()
            if not row:
                await ev.answer("No registrado.", alert=True); return
            flows[uid]["client_slug"]=row["slug"]
        else:
            with cx() as c:
                cur=c.cursor()
                cur.execute("SELECT slug FROM clients WHERE reseller_id=?", (str(uid),))
                slugs=[x["slug"] for x in cur.fetchall()]
            if not slugs:
                await ev.answer("No tienes clientes.", alert=True); return
            await ev.edit("Elige el cliente a renovar:", buttons=inline_pick_client(slugs)); return
        # si ya tenemos slug, mostrar términos
        with cx() as c:
            cur=c.cursor(); pr=prices(cur)
        txt, btn = inline_client_terms(pr)
        await ev.edit(txt, buttons=btn); return

    # reseller elige cliente
    if data.startswith("pay:cli:") and uid in flows and flows[uid]["mode"]=="pay":
        flows[uid]["client_slug"]=data.split(":",2)[2]
        with cx() as c:
            cur=c.cursor(); pr=prices(cur)
        txt, btn = inline_client_terms(pr)
        await ev.edit(txt, buttons=btn); return

    # elegir duración cliente
    if data in ("pay:c:30","pay:c:90","pay:c:365") and uid in flows and flows[uid]["mode"]=="pay":
        term = data.split(":")[2]
        with cx() as c:
            cur=c.cursor(); pr=prices(cur); rate=pr["usd_to_cup"]
            usd = {"30":pr["c30"],"90":pr["c90"],"365":pr["c365"]}[term]
            cup = int(usd*rate)
        flows[uid] |= {"step":"pay_method","plan_code":f"client_{term}","amount_usd":usd,"amount_cup":cup,
                       "item_id":flows[uid].get("client_slug")}
        txt, btn = inline_pay_methods(usd, cup)
        await ev.edit(txt, buttons=btn); return

    # método de pago
    if data in ("pay:m:saldo","pay:m:cup") and uid in flows and flows[uid]["mode"]=="pay":
        mtype = "saldo" if data.endswith("saldo") else "cup"
        f = flows[uid]; f["method"]=mtype; f["step"]="receipt"
        ps=get_setting("pay_text_saldo"); pc=get_setting("pay_text_cup")
        txt = (MSG_PAY_SALDO.format(txt=ps, monto_saldo=f["amount_cup"]) if mtype=="saldo"
               else MSG_PAY_CUP.format(txt=pc, monto_cup=f["amount_cup"]))
        await ev.edit(txt, buttons=btn_send_receipt()); return

    # subir comprobante
    if data == "pay:receipt" and uid in flows and flows[uid]["mode"]=="pay":
        flows[uid]["await_receipt"]=True
        await ev.answer("Adjunta la imagen del comprobante en el chat.", alert=True); return

# ---------- Entrada de datos (texto/medios) ----------
@bot.on(events.NewMessage)
async def flows_input(ev):
    uid=ev.sender_id
    if uid not in flows: return
    f=flows[uid]

    # crear cliente (reseller)
    if f.get("mode")=="newcli" and f.get("step")=="client_id":
        try: cid=int((ev.raw_text or "").strip())
        except: await ev.reply("❌ ID inválido", buttons=kb_reseller()); return
        with cx() as c:
            cur=c.cursor()
            cur.execute("SELECT plan,started,expires FROM resellers WHERE id=?", (f["rid"],))
            rr=cur.fetchone()
            if not rr: await ev.reply("❌ Reseller no existe", buttons=kb_reseller()); flows.pop(uid,None); return
            lims=limits(cur); lim=lims.get(rr["plan"],0)
            cur.execute("SELECT COUNT(*) AS n FROM clients WHERE reseller_id=?", (f["rid"],))
            used=cur.fetchone()["n"]
            if lim and used>=lim:
                await ev.reply(MSG_RES_LIMIT.format(limit=lim), buttons=kb_reseller()); flows.pop(uid,None); return
            # slug único + workdir
            slug = slugify(str(cid)); base=slug; i=2
            while True:
                cur.execute("SELECT 1 FROM clients WHERE slug=?", (slug,))
                if not cur.fetchone(): break
                slug=f"{base}{i}"; i+=1
            wdir = ensure_client_workdir(slug)
            cur.execute("""INSERT INTO clients(slug,owner_id,username,reseller_id,plan,expires,created,workdir,svc_status)
                           VALUES(?,?,?,?,?,?,?,?,?)""",
                        (slug, cid, None, f["rid"], "plan_estandar",
                         (dt.date.today()+dt.timedelta(days=30)).isoformat(),
                         iso_now(), str(wdir), "stopped"))
            c.commit()
        flows.pop(uid,None)
        await ev.reply(MSG_CREATED_CLIENT.format(slug=slug, rid=f["rid"]), buttons=kb_reseller())
        return

    # recepción de comprobante
    if f.get("mode")=="pay" and f.get("await_receipt"):
        if not (ev.photo or ev.document):
            await ev.reply("📎 Adjunta una **imagen** del comprobante."); return
        with cx() as c:
            cur=c.cursor()
            pid = new_id()
            cur.execute("""INSERT INTO payments(id,user_id,role,type,amount_usd,amount_cup,plan,item_id,receipt_msg_id,status,created,rate_used)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (pid, uid, f["as"], f["method"], f["amount_usd"], f["amount_cup"],
                         f.get("plan_code","res_b"), str(f.get("item_id") or uid),
                         ev.message.id, "pending", iso_now(), prices(cur)["usd_to_cup"]))
            c.commit()
        flows.pop(uid,None)
        await ev.reply(MSG_RECEIPT_OK)
        boss_id = int(get_setting("owner_id","0") or 0)
        if boss_id:
            try:
                await bot.send_message(boss_id, f"🧾 Pago pendiente de `{uid}`: {f['amount_usd']} USD ({f['amount_cup']} CUP) [{f['method']}]. ID: {pid}")
            except: pass
        return

# ---------- Pagos: listar/aprobar/rechazar (Boss) ----------
@bot.on(events.NewMessage(pattern=r"^💳 Pagos$|^/payments$"))
async def list_payments(ev):
    if role_for(ev.sender_id)!="boss": return
    with cx() as c:
        cur=cursor=c.cursor()
        cur.execute("SELECT id,user_id,role,type,amount_usd,amount_cup,status,plan,item_id,created FROM payments ORDER BY created DESC LIMIT 30")
        rows=cur.fetchall()
    if not rows: await ev.reply("📭 Sin pagos.", buttons=kb_boss()); return
    lines=["🧾 **Pagos recientes**"]+[
        f"• {r['id']} [{r['status']}] – {r['amount_usd']} USD / {r['amount_cup']} CUP – {r['role']}/{r['type']} – {r['plan']} – item {r['item_id']} – user {r['user_id']}"
        for r in rows
    ]
    lines.append("\nUsa: `/approve <id>`  o  `/reject <id> <motivo>`")
    await ev.reply("\n".join(lines), buttons=kb_boss())

@bot.on(events.NewMessage(pattern=r"^/approve\s+([a-f0-9]{10,})$"))
async def approve(ev):
    if role_for(ev.sender_id)!="boss": return
    pid = ev.pattern_match.group(1)
    with cx() as c:
        cur=c.cursor()
        cur.execute("SELECT * FROM payments WHERE id=?", (pid,)); p=cur.fetchone()
        if not p: await ev.reply("❌ No existe.", buttons=kb_boss()); return
        if p["status"]!="pending": await ev.reply("⚠️ No está pendiente.", buttons=kb_boss()); return

        # Aplicar efecto:
        if p["plan"].startswith("res_") and p["role"]=="reseller":
            rid = p["item_id"]
            # obtener plan actual y fechas
            cur.execute("SELECT plan,started,expires FROM resellers WHERE id=?", (rid,))
            r=cur.fetchone()
            if r:
                pr = prices(cur)
                old_base = pr[r["plan"]]
                new_base = pr[p["plan"]]
                extra = prorate(old_base, new_base, r["started"], r["expires"])
                # upgrade: cambiar plan, conservar expires
                cur.execute("UPDATE resellers SET plan=? WHERE id=?", (p["plan"], rid))
                # auditoría
                cur.execute("INSERT INTO audit(actor_id,action,meta,created) VALUES(?,?,?,?)",
                            (ev.sender_id, "approve_reseller_upgrade",
                             f"rid={rid}; old={r['plan']}; new={p['plan']}; extra={extra}", iso_now()))
        elif p["plan"].startswith("client_"):
            slug = p["item_id"]
            if p["plan"]=="client_30": days=30
            elif p["plan"]=="client_90": days=90
            else: days=365
            cur.execute("SELECT expires FROM clients WHERE slug=?", (slug,))
            r=cur.fetchone()
            base_date = dt.date.fromisoformat(r["expires"]) if r else dt.date.today()
            if base_date < dt.date.today(): base_date = dt.date.today()
            new_exp = (base_date + dt.timedelta(days=days)).isoformat()
            cur.execute("UPDATE clients SET expires=? WHERE slug=?", (new_exp, slug))
            cur.execute("INSERT INTO audit(actor_id,action,meta,created) VALUES(?,?,?,?)",
                        (ev.sender_id, "approve_client_renew", f"slug={slug}; +{days}d -> {new_exp}", iso_now()))
        # marcar pago aprobado
        cur.execute("UPDATE payments SET status='approved' WHERE id=?", (pid,))
        c.commit()

    await ev.reply(f"✅ Aprobado: {pid}", buttons=kb_boss())
    try: await bot.send_message(p["user_id"], "✅ Pago aprobado. ¡Gracias!")
    except: pass

@bot.on(events.NewMessage(pattern=r"^/reject\s+([a-f0-9]{10,})\s*(.*)$"))
async def reject(ev):
    if role_for(ev.sender_id)!="boss": return
    pid = ev.pattern_match.group(1); reason=(ev.pattern_match.group(2) or "Sin motivo").strip()
    with cx() as c:
        cur=c.cursor()
        cur.execute("SELECT user_id,status FROM payments WHERE id=?", (pid,))
        p=cur.fetchone()
        if not p: await ev.reply("❌ No existe.", buttons=kb_boss()); return
        if p["status"]!="pending": await ev.reply("⚠️ No está pendiente.", buttons=kb_boss()); return
        cur.execute("UPDATE payments SET status='rejected' WHERE id=?", (pid,)); c.commit()
    await ev.reply(f"❌ Rechazado: {pid}", buttons=kb_boss())
    try: await bot.send_message(p["user_id"], f"❌ Pago rechazado. Motivo: {reason}")
    except: pass

# ---------- Expiraciones ----------
async def expiry_loop():
    while True:
        try:
            today=dt.date.today().isoformat()
            with cx() as c:
                cur=c.cursor()
                # aviso -1 día
                cur.execute("SELECT owner_id,slug FROM clients WHERE date(expires)=date(?, '+1 day')",(today,))
                for r in cur.fetchall():
                    try: await bot.send_message(r["owner_id"], MSG_EXPIRES_TMR.format(slug=r["slug"]))
                    except: pass
                # vencidos
                cur.execute("SELECT owner_id,slug FROM clients WHERE date(expires)<=date(?)",(today,))
                for r in cur.fetchall():
                    try: await bot.send_message(r["owner_id"], MSG_EXPIRED.format(slug=r["slug"]))
                    except: pass
        except Exception as e:
            print("expiry:", e)
        await asyncio.sleep(3600)

# ---------- Main ----------
async def main():
    init_db()
    await bot.start(bot_token=SET.bot_token)
    print("✅ Reseller bot listo.")
    asyncio.create_task(expiry_loop())
    await bot.run_until_disconnected()

if __name__=="__main__":
    asyncio.run(main())
