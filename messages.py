"""
Mensajes para el bot en múltiples idiomas.
"""

MESSAGES = {
    "es": {
        "MSG_WELCOME_GUEST": (
            "👋 **¡Bienvenido(a)!**\n"
            "Aún no estás registrado en el sistema. Para comenzar, contacta a tu reseller o escribe a nuestro soporte en @{support_contact}.\n"
            "¡Estamos aquí para ayudarte!"
        ),
        "MSG_WELCOME_BOSS": (
            "👑 **Panel de Administrador**\n"
            "¡Bienvenido, jefe! Tienes control total del sistema. Desde aquí puedes:\n"
            "- Crear y gestionar resellers.\n"
            "- Configurar precios y tasas.\n"
            "- Aprobar o rechazar pagos.\n"
            "- Crear clientes directamente.\n\n"
            "Selecciona una opción para continuar:"
        ),
        "MSG_WELCOME_RESELLER": (
            "💼 **Panel de Reseller**\n"
            "¡Hola! Eres un reseller y puedes:\n"
            "- Crear y administrar clientes.\n"
            "- Renovar planes de clientes.\n"
            "- Consultar tu lista de clientes.\n\n"
            "Elige una acción para empezar:"
        ),
        "MSG_WELCOME_CLIENT": (
            "👤 **Hola, {username}!**\n"
            "Tu cuenta está activa. Aquí están los detalles de tu plan:\n"
            "- **Plan**: {plan}\n"
            "- **Vence**: {expires}\n"
            "- **Slug**: `{slug}`\n\n"
            "Usa los botones para renovar tu plan o contactar a tu reseller para soporte."
        ),
        "MSG_ERROR_NO_PERMISSION": (
            "🔒 **Acceso denegado**\n"
            "No tienes permisos para realizar esta acción. Verifica tu rol o contacta a soporte."
        ),
        "MSG_ERROR_INVALID_ID": (
            "❌ **ID inválido**\n"
            "El ID debe ser un número válido (por ejemplo, 123456789). Por favor, intenta de nuevo."
        ),
        "MSG_CLIENT_CREATED": (
            "🎉 **Cliente creado exitosamente**\n"
            "- **Slug**: `{slug}`\n"
            "- **Reseller ID**: `{rid}`\n"
            "- **Plan**: {plan}\n"
            "- **Vence**: `{expires}`\n\n"
            "El cliente ya puede usar el servicio. Notifícalo con su slug."
        ),
        "MSG_RESELLER_CREATED": (
            "🎉 **Reseller creado**\n"
            "- **ID**: `{rid}`\n"
            "- **Plan**: {plan}\n"
            "- **Vence**: `{expires}`\n\n"
            "El reseller ha sido registrado y puede comenzar a crear clientes."
        ),
        "MSG_PAYMENT_PICK": (
            "💳 **Realizar un pago**\n"
            "Selecciona qué quieres pagar o renovar:\n"
            "- **Plan Reseller**: Actualiza o renueva tu plan de reseller.\n"
            "- **Renovar Cliente**: Extiende el plan de un cliente existente."
        ),
        "MSG_PAYMENT_SALDO": (
            "💵 **Pagar con saldo**\n"
            "{txt}\n"
            "Monto a pagar: **{monto_saldo} CUP**\n\n"
            "Por favor, adjunta el comprobante de pago en el chat."
        ),
        "MSG_PAYMENT_CUP": (
            "💵 **Pagar en CUP**\n"
            "{txt}\n"
            "Monto a pagar: **{monto_cup} CUP**\n\n"
            "Por favor, adjunta el comprobante de pago en el chat."
        ),
        "MSG_PAYMENT_SUCCESS": (
            "✅ **Pago registrado**\n"
            "- **ID de transacción**: `{pid}`\n"
            "- **Monto**: {amount_usd} USD ({amount_cup} CUP)\n"
            "- **Método**: {method}\n"
            "- **Plan**: {plan}\n\n"
            "Tu pago está en revisión. Te notificaremos cuando sea aprobado."
        ),
        "MSG_EXPIRES_TOMORROW": (
            "⚠️ **Recordatorio de vencimiento**\n"
            "Tu plan `{slug}` vence **mañana** ({expires}).\n"
            "Renueva ahora para evitar interrupciones en el servicio."
        ),
        "MSG_EX
