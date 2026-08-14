import os
import io
import asyncio
from datetime import datetime
import qrcode

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ContentType
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from sqlalchemy import select, func, desc

from db import init_db, Session, User, Product, Order
from keyboards import *
from rvg_client import RVGClient, RVGError

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.getenv("OWNER_ID", "80145544"))
CARD_NUMBER = os.getenv("CARD_NUMBER", "")
CARD_HOLDER = os.getenv("CARD_HOLDER", "کرمی")
BOT_NAME = os.getenv("BOT_NAME", "RVG Store")
SUPPORT = os.getenv("SUPPORT_USERNAME", "repair_phone")

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
rvg = RVGClient()

class ReceiptState(StatesGroup):
    waiting = State()

class AdminInputState(StatesGroup):
    price = State()
    name = State()
    new_product = State()

def is_admin(uid: int) -> bool:
    return uid == OWNER_ID

async def upsert_user(tg):
    async with Session() as s:
        q = await s.execute(select(User).where(User.telegram_id == tg.id))
        u = q.scalar_one_or_none()
        if not u:
            u = User(telegram_id=tg.id, username=tg.username, first_name=tg.first_name)
            s.add(u)
        else:
            u.username, u.first_name = tg.username, tg.first_name
        await s.commit()
        return u.id

async def get_user_by_tg(tid):
    async with Session() as s:
        q = await s.execute(select(User).where(User.telegram_id == tid))
        return q.scalar_one_or_none()

async def product_list(active=True):
    async with Session() as s:
        q = select(Product)
        if active:
            q = q.where(Product.active.is_(True))
        q = q.order_by(Product.volume_gb)
        return list((await s.execute(q)).scalars().all())

async def fmt_order(order, product, user):
    return (
        f"🧾 <b>سفارش #{order.id}</b>\n"
        f"👤 کاربر: <code>{user.telegram_id}</code> "
        f"{('@'+user.username) if user.username else ''}\n"
        f"📦 پلن: {product.name} — {product.volume_gb}GB / {product.days} روز\n"
        f"💰 مبلغ: <b>{order.amount:,} تومان</b>\n"
        f"📌 وضعیت: <b>{order.status}</b>\n"
    )

async def send_qr(chat_id: int, link: str, label: str):
    img = qrcode.make(link)
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    await bot.send_photo(
        chat_id,
        BufferedInputFile(bio.read(), filename="config-qr.png"),
        caption=f"📱 <b>QR Code</b>\n{label}"
    )

@dp.message(CommandStart())
async def start(m: Message):
    await upsert_user(m.from_user)
    await m.answer(
        f"👋 <b>به {BOT_NAME} خوش آمدید</b>\n\n"
        "🛒 خرید کانفیگ، دریافت سرویس و پیگیری سفارش از همین ربات انجام می‌شود.",
        reply_markup=main_menu()
    )

@dp.message(Command("admin"))
async def admin_cmd(m: Message):
    if not is_admin(m.from_user.id):
        return
    await m.answer("👑 <b>پنل مدیریت</b>", reply_markup=admin_menu())

@dp.callback_query(F.data == "home")
async def home(c: CallbackQuery):
    await c.message.edit_text("🏠 <b>منوی اصلی</b>", reply_markup=main_menu())
    await c.answer()

@dp.callback_query(F.data == "buy")
async def buy(c: CallbackQuery):
    products = await product_list()
    if not products:
        await c.answer("فعلاً پلنی فعال نیست.", show_alert=True)
        return
    await c.message.edit_text("🛒 <b>پلن موردنظر را انتخاب کنید:</b>", reply_markup=products_kb(products))
    await c.answer()

@dp.callback_query(F.data.startswith("product:"))
async def select_product(c: CallbackQuery):
    pid = int(c.data.split(":")[1])
    async with Session() as s:
        p = await s.get(Product, pid)
        u = (await s.execute(select(User).where(User.telegram_id == c.from_user.id))).scalar_one_or_none()
        if not p or not p.active or not u:
            await c.answer("پلن در دسترس نیست.", show_alert=True)
            return
        order = Order(user_id=u.id, product_id=p.id, amount=p.price)
        s.add(order)
        await s.commit()
        await s.refresh(order)
        oid = order.id
    text = (
        f"🧾 <b>سفارش #{oid}</b>\n\n"
        f"📦 {p.name}\n"
        f"📊 حجم: {p.volume_gb}GB\n"
        f"📅 مدت: {p.days} روز\n"
        f"💰 مبلغ: <b>{p.price:,} تومان</b>\n\n"
        f"💳 <b>پرداخت کارت‌به‌کارت</b>\n"
        f"شماره کارت:\n<code>{CARD_NUMBER}</code>\n"
        f"به نام: <b>{CARD_HOLDER}</b>\n\n"
        "پس از پرداخت، روی «ارسال رسید پرداخت» بزنید و عکس رسید را ارسال کنید."
    )
    await c.message.edit_text(text, reply_markup=payment_kb(oid))
    await c.answer()

@dp.callback_query(F.data.startswith("receipt:"))
async def receipt_start(c: CallbackQuery, state: FSMContext):
    oid = int(c.data.split(":")[1])
    await state.set_state(ReceiptState.waiting)
    await state.update_data(order_id=oid)
    await c.message.answer("📤 لطفاً <b>عکس رسید پرداخت</b> را همینجا ارسال کنید.")
    await c.answer()

@dp.message(ReceiptState.waiting, F.content_type.in_({ContentType.PHOTO, ContentType.DOCUMENT}))
async def receipt_received(m: Message, state: FSMContext):
    data = await state.get_data()
    oid = int(data["order_id"])
    file_id = m.photo[-1].file_id if m.photo else m.document.file_id
    kind = "photo" if m.photo else "document"
    async with Session() as s:
        order = await s.get(Order, oid)
        if not order or order.status not in ("awaiting_receipt", "rejected"):
            await m.answer("این سفارش دیگر قابل ارسال نیست.")
            await state.clear()
            return
        order.receipt_file_id = file_id
        order.receipt_kind = kind
        order.status = "pending_review"
        await s.commit()
        p = await s.get(Product, order.product_id)
        u = await s.get(User, order.user_id)
    await state.clear()
    await m.answer("✅ رسید دریافت شد.\n⏳ سفارش برای بررسی ادمین ارسال شد.")
    caption = await fmt_order(order, p, u)
    caption += "\n📎 <b>رسید پرداخت بالا پیوست شده است.</b>"
    if kind == "photo":
        await bot.send_photo(OWNER_ID, file_id, caption=caption, reply_markup=admin_order_kb(oid))
    else:
        await bot.send_document(OWNER_ID, file_id, caption=caption, reply_markup=admin_order_kb(oid))

@dp.message(ReceiptState.waiting)
async def receipt_wrong(m: Message):
    await m.answer("لطفاً رسید را به‌صورت عکس یا فایل ارسال کنید.")

@dp.callback_query(F.data.startswith("cancel:"))
async def cancel_order(c: CallbackQuery):
    oid = int(c.data.split(":")[1])
    async with Session() as s:
        o = await s.get(Order, oid)
        if o and o.user_id == (await s.execute(select(User.id).where(User.telegram_id == c.from_user.id))).scalar_one_or_none():
            if o.status in ("awaiting_receipt", "rejected"):
                o.status = "cancelled"
                await s.commit()
    await c.message.edit_text("❌ سفارش لغو شد.", reply_markup=main_menu())
    await c.answer()

@dp.callback_query(F.data == "my_orders")
async def my_orders(c: CallbackQuery):
    u = await get_user_by_tg(c.from_user.id)
    if not u:
        return
    async with Session() as s:
        rows = list((await s.execute(
            select(Order, Product).join(Product, Product.id == Order.product_id)
            .where(Order.user_id == u.id).order_by(desc(Order.id)).limit(15)
        )).all())
    if not rows:
        text = "🧾 هنوز سفارشی ندارید."
    else:
        status_map = {
            "awaiting_receipt":"در انتظار رسید", "pending_review":"در انتظار بررسی",
            "paid":"تأیید شده", "delivered":"تحویل شده", "rejected":"رد شده", "cancelled":"لغو شده"
        }
        text = "🧾 <b>آخرین سفارش‌ها</b>\n\n" + "\n".join(
            f"#{o.id} — {p.volume_gb}GB/{p.days}روز — {o.amount:,} — {status_map.get(o.status,o.status)}"
            for o,p in rows
        )
    await c.message.edit_text(text, reply_markup=main_menu())
    await c.answer()

@dp.callback_query(F.data == "my_services")
async def my_services(c: CallbackQuery):
    u = await get_user_by_tg(c.from_user.id)
    if not u:
        return
    async with Session() as s:
        rows = list((await s.execute(
            select(Order, Product).join(Product, Product.id == Order.product_id)
            .where(Order.user_id == u.id, Order.status == "delivered", Order.config_link.is_not(None))
            .order_by(desc(Order.id)).limit(10)
        )).all())
    if not rows:
        text = "📦 هنوز سرویس فعالی ندارید."
    else:
        text = "📦 <b>سرویس‌های من</b>\n\n"
        for o,p in rows:
            text += f"🟢 <b>#{o.id}</b> — {p.volume_gb}GB / {p.days} روز\n🔗 <code>{o.config_link}</code>\n\n"
    await c.message.edit_text(text, reply_markup=main_menu())
    await c.answer()

@dp.callback_query(F.data == "help")
async def help_cb(c: CallbackQuery):
    await c.message.edit_text(
        "📚 <b>آموزش اتصال</b>\n\n"
        "برای اندروید/آیفون/ویندوز از یک کلاینت سازگار با VLESS استفاده کنید.\n"
        "در مرحله بعد می‌توانیم آموزش اختصاصی هر سیستم‌عامل را داخل ربات اضافه کنیم.",
        reply_markup=main_menu()
    )
    await c.answer()

@dp.callback_query(F.data == "support")
async def support(c: CallbackQuery):
    await c.message.edit_text(f"📞 پشتیبانی: @{SUPPORT}", reply_markup=main_menu())
    await c.answer()

async def load_order_bundle(s, oid):
    o = await s.get(Order, oid)
    if not o:
        return None
    p = await s.get(Product, o.product_id)
    u = await s.get(User, o.user_id)
    return o,p,u

@dp.callback_query(F.data.startswith("approve:"))
async def approve(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("دسترسی ندارید.", show_alert=True); return
    oid = int(c.data.split(":")[1])
    async with Session() as s:
        o,p,u = await load_order_bundle(s, oid)
        if not o or o.status != "pending_review":
            await c.answer("این سفارش قبلاً بررسی شده یا وضعیتش تغییر کرده.", show_alert=True); return
        o.status = "paid"
        o.paid_at = datetime.utcnow()
        o.admin_id = c.from_user.id
        await s.commit()
        await s.refresh(o)
    await c.answer("پرداخت تأیید شد؛ در حال ساخت کانفیگ...")
    try:
        result = await rvg.create_config(
            label=f"TG-{u.telegram_id}-O{oid}",
            volume_gb=p.volume_gb,
            days=p.days,
            protocol=p.protocol
        )
        async with Session() as s:
            o = await s.get(Order, oid)
            o.rvg_uuid = result.get("uuid")
            o.config_link = result.get("vless_link")
            o.sub_url = result.get("sub_url")
            o.status = "delivered"
            o.delivered_at = datetime.utcnow()
            await s.commit()
        await bot.send_message(
            u.telegram_id,
            f"🎉 <b>پرداخت شما تأیید شد!</b>\n\n"
            f"📦 {p.name}\n📊 {p.volume_gb}GB\n📅 {p.days} روز\n\n"
            f"🔗 <b>لینک کانفیگ:</b>\n<code>{result['vless_link']}</code>\n\n"
            f"🔄 <b>Subscription:</b>\n<code>{result['sub_url']}</code>"
        )
        await send_qr(u.telegram_id, result["vless_link"], p.name)
        await bot.send_message(OWNER_ID, f"✅ سفارش #{oid} تحویل شد و کانفیگ برای مشتری ارسال شد.")
        try:
            await c.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
    except Exception as e:
        async with Session() as s:
            o = await s.get(Order, oid)
            if o:
                o.status = "paid"
                await s.commit()
        await bot.send_message(
            OWNER_ID,
            f"⚠️ پرداخت سفارش #{oid} تأیید شد اما ساخت کانفیگ ناموفق بود:\n<code>{str(e)[:1500]}</code>"
        )

@dp.callback_query(F.data.startswith("reject:"))
async def reject(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("دسترسی ندارید.", show_alert=True); return
    oid = int(c.data.split(":")[1])
    async with Session() as s:
        o,p,u = await load_order_bundle(s, oid)
        if not o or o.status != "pending_review":
            await c.answer("سفارش قابل رد نیست.", show_alert=True); return
        o.status = "rejected"
        o.admin_id = c.from_user.id
        o.reject_reason = "توسط ادمین رد شد"
        await s.commit()
    await bot.send_message(u.telegram_id, f"❌ <b>رسید سفارش #{oid} تأیید نشد.</b>\nلطفاً رسید صحیح را ارسال کنید.")
    await c.message.edit_reply_markup(reply_markup=None)
    await c.answer("سفارش رد شد.")

@dp.callback_query(F.data == "admin")
async def admin_panel(c: CallbackQuery):
    if not is_admin(c.from_user.id): return
    await c.message.edit_text("👑 <b>پنل مدیریت حرفه‌ای</b>", reply_markup=admin_menu())
    await c.answer()

@dp.callback_query(F.data == "adm:dashboard")
async def admin_dashboard(c: CallbackQuery):
    if not is_admin(c.from_user.id): return
    async with Session() as s:
        users = await s.scalar(select(func.count()).select_from(User))
        orders = await s.scalar(select(func.count()).select_from(Order))
        pending = await s.scalar(select(func.count()).select_from(Order).where(Order.status=="pending_review"))
        delivered = await s.scalar(select(func.count()).select_from(Order).where(Order.status=="delivered"))
        revenue = await s.scalar(select(func.coalesce(func.sum(Order.amount),0)).where(Order.status.in_(["paid","delivered"])))
    await c.message.edit_text(
        f"📊 <b>داشبورد</b>\n\n👥 کاربران: <b>{users}</b>\n🧾 سفارش‌ها: <b>{orders}</b>\n"
        f"🟡 در انتظار بررسی: <b>{pending}</b>\n🟢 تحویل‌شده: <b>{delivered}</b>\n"
        f"💰 فروش ثبت‌شده: <b>{int(revenue or 0):,} تومان</b>",
        reply_markup=admin_menu()
    )
    await c.answer()

@dp.callback_query(F.data == "adm:pending")
async def admin_pending(c: CallbackQuery):
    if not is_admin(c.from_user.id): return
    async with Session() as s:
        rows = list((await s.execute(
            select(Order, Product, User).join(Product, Product.id==Order.product_id).join(User, User.id==Order.user_id)
            .where(Order.status=="pending_review").order_by(Order.id)
        )).all())
    if not rows:
        await c.message.edit_text("🟢 سفارشی در انتظار بررسی نیست.", reply_markup=admin_menu())
        await c.answer(); return
    text = "🟡 <b>سفارش‌های در انتظار بررسی</b>\n\n"
    for o,p,u in rows[:20]:
        text += f"#{o.id} | {p.volume_gb}GB | {o.amount:,} تومان | {u.telegram_id}\n"
    kb = []
    for o,_,_ in rows[:20]:
        kb.append([InlineKeyboardButton(text=f"🧾 سفارش #{o.id}", callback_data=f"order:{o.id}")])
    kb.append([InlineKeyboardButton(text="🔙 مدیریت", callback_data="admin")])
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await c.answer()

@dp.callback_query(F.data.startswith("order:"))
async def admin_order(c: CallbackQuery):
    if not is_admin(c.from_user.id): return
    oid = int(c.data.split(":")[1])
    async with Session() as s:
        o,p,u = await load_order_bundle(s, oid)
    if not o:
        await c.answer("یافت نشد.", show_alert=True); return
    caption = await fmt_order(o,p,u)
    if o.receipt_file_id:
        if o.receipt_kind == "photo":
            await c.message.answer_photo(o.receipt_file_id, caption=caption, reply_markup=admin_order_kb(oid))
        else:
            await c.message.answer_document(o.receipt_file_id, caption=caption, reply_markup=admin_order_kb(oid))
    else:
        await c.message.answer(caption, reply_markup=admin_order_kb(oid))
    await c.answer()

@dp.callback_query(F.data == "adm:products")
async def adm_products(c: CallbackQuery):
    if not is_admin(c.from_user.id): return
    products = await product_list(active=False)
    await c.message.edit_text("📦 <b>مدیریت پلن‌ها</b>", reply_markup=product_admin_kb(products))
    await c.answer()

@dp.callback_query(F.data.startswith("admp:"))
async def adm_product(c: CallbackQuery):
    if not is_admin(c.from_user.id): return
    pid=int(c.data.split(":")[1])
    async with Session() as s: p=await s.get(Product,pid)
    if not p: await c.answer("یافت نشد.", show_alert=True); return
    await c.message.edit_text(
        f"📦 <b>{p.name}</b>\nحجم: {p.volume_gb}GB\nمدت: {p.days} روز\nقیمت: {p.price:,} تومان\n"
        f"وضعیت: {'🟢 فعال' if p.active else '🔴 غیرفعال'}",
        reply_markup=product_edit_kb(pid)
    )
    await c.answer()

@dp.callback_query(F.data.startswith("toggle:"))
async def toggle_product(c: CallbackQuery):
    if not is_admin(c.from_user.id): return
    pid=int(c.data.split(":")[1])
    async with Session() as s:
        p=await s.get(Product,pid); p.active=not p.active; await s.commit()
    await c.answer("وضعیت تغییر کرد.")
    await adm_product(c)

@dp.callback_query(F.data.startswith("deleteproduct:"))
async def delete_product(c: CallbackQuery):
    if not is_admin(c.from_user.id): return
    pid=int(c.data.split(":")[1])
    async with Session() as s:
        p=await s.get(Product,pid)
        if p: await s.delete(p); await s.commit()
    await c.answer("پلن حذف شد.")
    await adm_products(c)

@dp.callback_query(F.data.startswith("editprice:"))
async def edit_price(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return
    pid=int(c.data.split(":")[1])
    await state.set_state(AdminInputState.price); await state.update_data(pid=pid)
    await c.message.answer("💰 قیمت جدید را فقط به تومان وارد کن:")
    await c.answer()

@dp.message(AdminInputState.price)
async def set_price(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    try: price=int(m.text.replace(",","").replace(" ",""))
    except: await m.answer("عدد نامعتبر است."); return
    data=await state.get_data(); pid=int(data["pid"])
    async with Session() as s:
        p=await s.get(Product,pid); p.price=price; await s.commit()
    await state.clear(); await m.answer("✅ قیمت تغییر کرد.", reply_markup=admin_menu())

@dp.callback_query(F.data.startswith("editname:"))
async def edit_name(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return
    pid=int(c.data.split(":")[1])
    await state.set_state(AdminInputState.name); await state.update_data(pid=pid)
    await c.message.answer("✏️ نام جدید پلن:")
    await c.answer()

@dp.message(AdminInputState.name)
async def set_name(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    data=await state.get_data(); pid=int(data["pid"])
    async with Session() as s:
        p=await s.get(Product,pid); p.name=m.text[:100]; await s.commit()
    await state.clear(); await m.answer("✅ نام تغییر کرد.", reply_markup=admin_menu())

@dp.callback_query(F.data == "adm:add_product")
async def add_product_start(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return
    await state.set_state(AdminInputState.new_product)
    await c.message.answer(
        "➕ افزودن پلن\nفرمت:\n<b>نام | حجم GB | روز | قیمت تومان</b>\nمثال:\nاقتصادی | 30 | 30 | 150000"
    )
    await c.answer()

@dp.message(AdminInputState.new_product)
async def add_product_finish(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    parts=[x.strip() for x in (m.text or "").split("|")]
    if len(parts)!=4:
        await m.answer("فرمت اشتباه است."); return
    try: name,vol,days,price=parts[0],int(parts[1]),int(parts[2]),int(parts[3])
    except:
        await m.answer("حجم، روز و قیمت باید عدد باشند."); return
    async with Session() as s:
        s.add(Product(name=name,volume_gb=vol,days=days,price=price,protocol="vless-ws"))
        await s.commit()
    await state.clear(); await m.answer("✅ پلن اضافه شد.", reply_markup=admin_menu())

@dp.callback_query(F.data == "adm:users")
async def adm_users(c: CallbackQuery):
    if not is_admin(c.from_user.id): return
    async with Session() as s:
        count=await s.scalar(select(func.count()).select_from(User))
        blocked=await s.scalar(select(func.count()).select_from(User).where(User.is_blocked.is_(True)))
    await c.message.edit_text(f"👥 <b>کاربران</b>\n\nکل: {count}\nمسدود: {blocked}\n\nمدیریت جزئی کاربران را در نسخه بعد می‌توانیم به جستجو/مسدودسازی/سرویس‌ها گسترش دهیم.", reply_markup=admin_menu())
    await c.answer()

@dp.callback_query(F.data == "adm:sales")
async def adm_sales(c: CallbackQuery):
    if not is_admin(c.from_user.id): return
    async with Session() as s:
        revenue=await s.scalar(select(func.coalesce(func.sum(Order.amount),0)).where(Order.status.in_(["paid","delivered"])))
        today=await s.scalar(select(func.coalesce(func.sum(Order.amount),0)).where(Order.status.in_(["paid","delivered"]), func.date(Order.paid_at)==func.date(func.current_timestamp())))
        delivered=await s.scalar(select(func.count()).select_from(Order).where(Order.status=="delivered"))
    await c.message.edit_text(f"📈 <b>گزارش فروش</b>\n\n💰 کل: {int(revenue or 0):,} تومان\n📅 امروز: {int(today or 0):,} تومان\n🟢 سرویس تحویل‌شده: {delivered}", reply_markup=admin_menu())
    await c.answer()

@dp.callback_query(F.data == "adm:settings")
async def adm_settings(c: CallbackQuery):
    if not is_admin(c.from_user.id): return
    await c.message.edit_text(
        "⚙️ <b>تنظیمات</b>\n\n"
        f"💳 کارت: <code>{CARD_NUMBER}</code>\n"
        f"👤 صاحب حساب: {CARD_HOLDER}\n"
        f"🖥 RVG: {rvg.base}\n"
        f"👑 Owner ID: {OWNER_ID}\n\n"
        "اطلاعات حساس از Environment Variables خوانده می‌شوند.",
        reply_markup=admin_menu()
    )
    await c.answer()

async def main():
    await init_db()
    # seed initial plans only if database is empty
    async with Session() as s:
        count = await s.scalar(select(func.count()).select_from(Product))
        if not count:
            s.add_all([
                Product(name="اقتصادی", volume_gb=30, days=30, price=0, protocol="vless-ws"),
                Product(name="استاندارد", volume_gb=50, days=30, price=0, protocol="vless-ws"),
                Product(name="حرفه‌ای", volume_gb=100, days=30, price=0, protocol="vless-ws"),
            ])
            await s.commit()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
