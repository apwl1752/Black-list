import discord
from discord.ext import commands
from discord import app_commands
import json
import os
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
    embed.add_field(name="👤  الاسم",  value=f"```{name}```",                      inline=True)
    embed.add_field(name="📞  الجوال", value=f"```{contact.get('phone', '—')}```", inline=True)
    embed.add_field(name="\u200b",     value="\u200b",                             inline=True)
    embed.set_footer(text=f"🕒  أُضيف: {contact.get('added_at', '—')}")
    # الصورة تُرفق كـ image في الـ embed
    if contact.get("image_url"):
        embed.set_image(url=contact["image_url"])
    return embed

# ─── Events ───────────────────────────────────────────────
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ {bot.user} شغّال!")


# ══════════════════════════════════════════════════════════
#  ADD FLOW
#  الخطوة 1: Modal (Name + Phone)
#  الخطوة 2: رسالة تطلب رفع صورة → يرفع المستخدم صورة → بوت يحفظ
# ══════════════════════════════════════════════════════════

# نخزن البيانات المؤقتة هنا بانتظار الصورة  { user_id: {name, phone} }
pending_add: dict[int, dict] = {}
pending_edit: dict[int, dict] = {}  # { user_id: {name, phone, old_key} }


class AddModal(discord.ui.Modal, title="➕ إضافة جهة اتصال"):
    name  = discord.ui.TextInput(label="الاسم",  placeholder="أدخل الاسم",        required=True)
    phone = discord.ui.TextInput(label="الجوال", placeholder="مثال: 0501234567",  required=True)

    async def on_submit(self, interaction: discord.Interaction):
        data = load_data()
        if find_contact(data, str(self.name)):
            await interaction.response.send_message(
                f"⚠️ **{self.name}** موجود مسبقاً. استخدم `/edit`.", ephemeral=True
            )
            return

        # نخزن مؤقتاً وننتظر الصورة
        pending_add[interaction.user.id] = {
            "name":  str(self.name),
            "phone": str(self.phone),
        }

        await interaction.response.send_message(
            f"✅ **الخطوة 1 تمت!**\n"
            f"الآن **أرسل صورة** في نفس القناة لإكمال إضافة `{self.name}` 📸\n"
            f"*(لديك 2 دقيقة)*",
            ephemeral=True
        )


# ─── /add ─────────────────────────────────────────────────
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
    name  = discord.ui.TextInput(label="الاسم",  required=True)
    phone = discord.ui.TextInput(label="الجوال", required=True)

    def __init__(self, old_key: str, contact: dict):
        super().__init__()
        self.old_key      = old_key
        self.name.default  = old_key
        self.phone.default = contact.get("phone", "")

    async def on_submit(self, interaction: discord.Interaction):
        pending_edit[interaction.user.id] = {
            "old_key": self.old_key,
            "name":    str(self.name),
            "phone":   str(self.phone),
        }

        await interaction.response.send_message(
            f"✅ **الخطوة 1 تمت!**\n"
            f"الآن **أرسل صورة جديدة** في نفس القناة لإكمال التعديل 📸\n"
            f"*(لديك 2 دقيقة — أرسل الصورة القديمة إذا ما تبي تغيرها)*",
            ephemeral=True
        )


# ─── /edit ────────────────────────────────────────────────
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
#  on_message — يستقبل الصورة ويكمل الحفظ
# ══════════════════════════════════════════════════════════

@bot.event
async def on_message(message: discord.Message):
    # تجاهل رسائل البوت نفسه
    if message.author.bot:
        return

    uid = message.author.id

    # ── ADD ──────────────────────────────────────────────
    if uid in pending_add:
        # تحقق أن الرسالة فيها صورة
        image_url = None
        for att in message.attachments:
            if att.content_type and att.content_type.startswith("image/"):
                image_url = att.url
                break

        if not image_url:
            await message.reply("⚠️ لازم ترفق **صورة** لإكمال الإضافة! أرسل الصورة مباشرة.", mention_author=False)
            return

        info = pending_add.pop(uid)
        data = load_data()

        data[info["name"]] = {
            "phone":     info["phone"],
            "image_url": image_url,
            "added_at":  datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        save_data(data)

        embed = build_embed("✅ تمت الإضافة", data[info["name"]], info["name"], 0x2ecc71)
        await message.reply(embed=embed, mention_author=False)
        return

    # ── EDIT ─────────────────────────────────────────────
    if uid in pending_edit:
        image_url = None
        for att in message.attachments:
            if att.content_type and att.content_type.startswith("image/"):
                image_url = att.url
                break

        if not image_url:
            await message.reply("⚠️ لازم ترفق **صورة** لإكمال التعديل! أرسل الصورة مباشرة.", mention_author=False)
            return

        info = pending_edit.pop(uid)
        data = load_data()

        old_contact = data.get(info["old_key"], {})

        # احذف المفتاح القديم إذا تغير الاسم
        if info["old_key"] in data:
            del data[info["old_key"]]

        data[info["name"]] = {
            "phone":     info["phone"],
            "image_url": image_url,
            "added_at":  old_contact.get("added_at", "—"),
        }
        save_data(data)

        embed = build_embed("✅ تم التعديل", data[info["name"]], info["name"], 0xf39c12)
        await message.reply(embed=embed, mention_author=False)
        return

    await bot.process_commands(message)


# ══════════════════════════════════════════════════════════
#  VIEW / INFO / DELETE
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
