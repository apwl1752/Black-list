import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import asyncio
from datetime import datetime

# ─── Config ───────────────────────────────────────────────
TOKEN = os.environ.get("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE")
ALLOWED_CHANNEL_ID = int(os.environ.get("CHANNEL_ID", 0)) or None
DATA_FILE = "contacts.json"

# ─── Setup ────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ─── Data Helpers ─────────────────────────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def channel_check(interaction: discord.Interaction):
    if ALLOWED_CHANNEL_ID and interaction.channel_id != ALLOWED_CHANNEL_ID:
        return False
    return True

def find_contact(data, name):
    return next((k for k in data if k.lower() == name.lower()), None)

def build_embed(title, contact, name, color):
    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="👤  الاسم",  value=f"```{name}```",                       inline=True)
    embed.add_field(name="📞  الجوال", value=f"```{contact.get('phone', '—')}```",  inline=True)
    embed.add_field(name="\u200b",     value="\u200b",                              inline=True)
    embed.add_field(name="📝  السبب",  value=f"```{contact.get('reason', '—')}```", inline=False)
    embed.set_footer(text=f"🕒  أُضيف: {contact.get('added_at', '—')}")
    if contact.get("image_url"):
        embed.set_image(url=contact["image_url"])
    return embed

# ─── Events ───────────────────────────────────────────────
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ {bot.user} شغّال!")


# ══════════════════════════════════════════════════════════
#  pending dicts  { user_id: {data..., "_task": asyncio.Task} }
# ══════════════════════════════════════════════════════════
pending_add: dict[int, dict] = {}
pending_edit: dict[int, dict] = {}

TIMEOUT = 60  # ثانية

async def expire_pending(uid: int, store: dict, interaction: discord.Interaction):
    """ينتظر TIMEOUT ثانية — إذا ما رسل صور يمسح الـ pending ويحدث الرسالة"""
    await asyncio.sleep(TIMEOUT)
    if uid in store:
        store.pop(uid, None)
        try:
            await interaction.edit_original_response(
                content="⏰ **انتهى الوقت!**\nأرسل الأمر من جديد وأرسل الصور خلال 60 ثانية."
            )
        except Exception:
            pass


# ══════════════════════════════════════════════════════════
#  ADD FLOW
# ══════════════════════════════════════════════════════════

class AddModal(discord.ui.Modal, title="➕ إضافة جهة اتصال"):
    name   = discord.ui.TextInput(label="الاسم",  placeholder="أدخل الاسم",       required=True)
    phone  = discord.ui.TextInput(label="الجوال", placeholder="مثال: 0501234567", required=True)
    reason = discord.ui.TextInput(label="السبب",  placeholder="سبب الإضافة",      required=True,
                                  style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        data = load_data()
        if find_contact(data, str(self.name)):
            await interaction.response.send_message(
                f"⚠️ **{self.name}** موجود مسبقاً. استخدم `/edit`.", ephemeral=True
            )
            return

        pending_add[interaction.user.id] = {
            "name":   str(self.name),
            "phone":  str(self.phone),
            "reason": str(self.reason),
        }

        await interaction.response.send_message(
            f"✅ **الخطوة 1 تمت!**\n"
            f"الآن **أرسل صور الدليل** في نفس القناة 📸 *(1-10 صور)*\n"
            f"⏰ لديك **60 ثانية** وإلا يلغى الأمر.",
            ephemeral=True
        )
        task = asyncio.create_task(expire_pending(interaction.user.id, pending_add, interaction))
        pending_add[interaction.user.id]["_task"] = task


@bot.tree.command(name="add", description="➕ إضافة جهة اتصال جديدة")
async def add_contact(interaction: discord.Interaction):
    if not channel_check(interaction):
        await interaction.response.send_message("❌ هذا الأمر يشتغل في الروم المحددة فقط.", ephemeral=True)
        return
    await interaction.response.send_modal(AddModal())


# ══════════════════════════════════════════════════════════
#  EDIT FLOW
# ══════════════════════════════════════════════════════════

class EditModal(discord.ui.Modal, title="✏️ تعديل جهة اتصال"):
    name   = discord.ui.TextInput(label="الاسم",  required=True)
    phone  = discord.ui.TextInput(label="الجوال", required=True)
    reason = discord.ui.TextInput(label="السبب",  required=True,
                                  style=discord.TextStyle.paragraph)

    def __init__(self, old_key: str, contact: dict):
        super().__init__()
        self.old_key        = old_key
        self.name.default   = old_key
        self.phone.default  = contact.get("phone", "")
        self.reason.default = contact.get("reason", "")

    async def on_submit(self, interaction: discord.Interaction):
        pending_edit[interaction.user.id] = {
            "old_key": self.old_key,
            "name":    str(self.name),
            "phone":   str(self.phone),
            "reason":  str(self.reason),
        }

        await interaction.response.send_message(
            f"✅ **الخطوة 1 تمت!**\n"
            f"الآن **أرسل صور الدليل** في نفس القناة 📸 *(1-10 صور)*\n"
            f"⏰ لديك **60 ثانية** وإلا يلغى الأمر.",
            ephemeral=True
        )
        task = asyncio.create_task(expire_pending(interaction.user.id, pending_edit, interaction))
        pending_edit[interaction.user.id]["_task"] = task


@bot.tree.command(name="edit", description="✏️ تعديل جهة اتصال")
@app_commands.describe(name="اسم جهة الاتصال")
async def edit_contact(interaction: discord.Interaction, name: str):
    if not channel_check(interaction):
        await interaction.response.send_message("❌ هذا الأمر يشتغل في الروم المحددة فقط.", ephemeral=True)
        return
    data = load_data()
    match = find_contact(data, name)
    if not match:
        await interaction.response.send_message(f"❌ ما لقيت **{name}**.", ephemeral=True)
        return
    await interaction.response.send_modal(EditModal(old_key=match, contact=data[match]))


# ══════════════════════════════════════════════════════════
#  on_message — يستقبل الصورة، يحذف رسالة المستخدم، يرسل embed
# ══════════════════════════════════════════════════════════

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    uid = message.author.id

    # ── ADD ──────────────────────────────────────────────
    if uid in pending_add:
        image_atts = [att for att in message.attachments
                      if att.content_type and att.content_type.startswith("image/")]

        if not image_atts:
            await message.reply("⚠️ لازم ترفق **صورة الدليل** على الأقل!", mention_author=False)
            return

        # ألغِ الـ timeout task
        if "_task" in pending_add.get(uid, {}):
            pending_add[uid]["_task"].cancel()

        # اسحب كل الصور كـ files قبل الحذف (الحد 10)
        files = [await att.to_file() for att in image_atts[:10]]

        # احذف رسالة المستخدم
        try:
            await message.delete()
        except discord.Forbidden:
            pass

        info = pending_add.pop(uid)
        data = load_data()

        data[info["name"]] = {
            "phone":     info["phone"],
            "reason":    info["reason"],
            "image_url": image_atts[0].url,
            "added_at":  datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        save_data(data)

        # الـ embed يعرض أول صورة، والباقي ترفع معاه تلقائياً
        embed = build_embed("✅ تمت الإضافة", data[info["name"]], info["name"], 0x2ecc71)
        # نرسل الصور أولاً كلها مع بعض، ثم الـ embed منفصل
        await message.channel.send(files=files)
        await message.channel.send(embed=embed)
        return

    # ── EDIT ─────────────────────────────────────────────
    if uid in pending_edit:
        image_atts = [att for att in message.attachments
                      if att.content_type and att.content_type.startswith("image/")]

        if not image_atts:
            await message.reply("⚠️ لازم ترفق **صورة الدليل** على الأقل!", mention_author=False)
            return

        # ألغِ الـ timeout task
        if "_task" in pending_edit.get(uid, {}):
            pending_edit[uid]["_task"].cancel()

        files = [await att.to_file() for att in image_atts[:10]]

        try:
            await message.delete()
        except discord.Forbidden:
            pass

        info = pending_edit.pop(uid)
        data = load_data()
        old_contact = data.get(info["old_key"], {})

        if info["old_key"] in data:
            del data[info["old_key"]]

        data[info["name"]] = {
            "phone":     info["phone"],
            "reason":    info["reason"],
            "image_url": image_atts[0].url,
            "added_at":  old_contact.get("added_at", "—"),
        }
        save_data(data)

        embed = build_embed("✅ تم التعديل", data[info["name"]], info["name"], 0xf39c12)
        await message.channel.send(files=files)
        await message.channel.send(embed=embed)
        return

    await bot.process_commands(message)


# ══════════════════════════════════════════════════════════
#  VIEW / DELETE
# ══════════════════════════════════════════════════════════

@bot.tree.command(name="view", description="👁️ عرض جهة اتصال")
@app_commands.describe(name="الاسم")
async def view_contact(interaction: discord.Interaction, name: str):
    if not channel_check(interaction):
        await interaction.response.send_message("❌ هذا الأمر يشتغل في الروم المحددة فقط.", ephemeral=True)
        return
    data = load_data()
    match = find_contact(data, name)
    if not match:
        await interaction.response.send_message(f"❌ ما لقيت **{name}**.", ephemeral=True)
        return
    embed = build_embed(f"📋 {match}", data[match], match, 0x3498db)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="delete", description="🗑️ حذف جهة اتصال")
@app_commands.describe(name="الاسم")
async def delete_contact(interaction: discord.Interaction, name: str):
    if not channel_check(interaction):
        await interaction.response.send_message("❌ هذا الأمر يشتغل في الروم المحددة فقط.", ephemeral=True)
        return
    data = load_data()
    match = find_contact(data, name)
    if not match:
        await interaction.response.send_message(f"❌ ما لقيت **{name}**.", ephemeral=True)
        return
    del data[match]
    save_data(data)
    await interaction.response.send_message(f"🗑️ تم حذف **{match}** بنجاح.")


# ─── Run ──────────────────────────────────────────────────
bot.run(TOKEN)
