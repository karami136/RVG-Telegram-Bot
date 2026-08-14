from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 خرید کانفیگ", callback_data="buy")],
        [InlineKeyboardButton(text="📦 سرویس‌های من", callback_data="my_services"),
         InlineKeyboardButton(text="🧾 سفارش‌های من", callback_data="my_orders")],
        [InlineKeyboardButton(text="📚 آموزش اتصال", callback_data="help"),
         InlineKeyboardButton(text="📞 پشتیبانی", callback_data="support")],
    ])

def products_kb(products):
    rows = []
    for p in products:
        rows.append([InlineKeyboardButton(
            text=f"📦 {p.name} | {p.volume_gb}GB / {p.days} روز | {p.price:,} تومان",
            callback_data=f"product:{p.id}"
        )])
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def payment_kb(order_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 ارسال رسید پرداخت", callback_data=f"receipt:{order_id}")],
        [InlineKeyboardButton(text="❌ لغو سفارش", callback_data=f"cancel:{order_id}")]
    ])

def admin_order_kb(order_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ تأیید پرداخت", callback_data=f"approve:{order_id}")],
        [InlineKeyboardButton(text="❌ رد پرداخت", callback_data=f"reject:{order_id}")],
        [InlineKeyboardButton(text="🔄 بازخوانی", callback_data=f"order:{order_id}")],
    ])

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 داشبورد", callback_data="adm:dashboard")],
        [InlineKeyboardButton(text="🧾 سفارش‌های در انتظار", callback_data="adm:pending")],
        [InlineKeyboardButton(text="📦 مدیریت پلن‌ها", callback_data="adm:products")],
        [InlineKeyboardButton(text="👥 کاربران", callback_data="adm:users"),
         InlineKeyboardButton(text="📈 فروش", callback_data="adm:sales")],
        [InlineKeyboardButton(text="⚙️ تنظیمات", callback_data="adm:settings")],
    ])

def product_admin_kb(products):
    rows = []
    for p in products:
        status = "🟢" if p.active else "🔴"
        rows.append([InlineKeyboardButton(
            text=f"{status} {p.name} | {p.volume_gb}GB | {p.price:,}",
            callback_data=f"admp:{p.id}"
        )])
    rows += [
        [InlineKeyboardButton(text="➕ افزودن پلن", callback_data="adm:add_product")],
        [InlineKeyboardButton(text="🔙 پنل مدیریت", callback_data="admin")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def product_edit_kb(pid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 تغییر قیمت", callback_data=f"editprice:{pid}")],
        [InlineKeyboardButton(text="✏️ تغییر نام", callback_data=f"editname:{pid}")],
        [InlineKeyboardButton(text="🔄 فعال/غیرفعال", callback_data=f"toggle:{pid}")],
        [InlineKeyboardButton(text="🗑 حذف پلن", callback_data=f"deleteproduct:{pid}")],
        [InlineKeyboardButton(text="🔙 پلن‌ها", callback_data="adm:products")]
    ])
