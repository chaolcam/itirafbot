import telebot
import os
import sys
import time
import datetime
import signal
from threading import Thread
from flask import Flask
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import pymongo
from dotenv import load_dotenv

# Logların Render konsolunda anında görünmesi için unbuffered output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

# .env dosyasını yükle (varsa)
load_dotenv()

# --- AYARLAR VE ÇEVRE DEĞİŞKENLERİ ---
TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")

ADMIN_GROUP_ID = int(os.environ.get("ADMIN_GROUP_ID", "-1003791676374"))
TARGET_CHANNEL_ID = int(os.environ.get("TARGET_CHANNEL_ID", "-1003983042944"))
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "resimpuanla").replace("@", "")
CHANNEL_INVITE_LINK = os.environ.get("CHANNEL_INVITE_LINK", "")
BACKUP_CHANNEL_ID_ENV = os.environ.get("BACKUP_CHANNEL_ID", "")
BACKUP_CHANNEL_ID = int(BACKUP_CHANNEL_ID_ENV) if BACKUP_CHANNEL_ID_ENV else None

PATRON_ID = int(os.environ.get("PATRON_ID", "7075582251"))

if not TOKEN:
    print("UYARI: BOT_TOKEN çevresel değişkeni tanımlanmamış!")

bot = telebot.TeleBot(TOKEN) if TOKEN else None

BOT_USERNAME = os.environ.get("BOT_USERNAME", "").replace("@", "")

def get_bot_username():
    global BOT_USERNAME
    if not BOT_USERNAME and bot:
        try:
            me = bot.get_me()
            BOT_USERNAME = me.username
        except Exception:
            pass
    return BOT_USERNAME or ""

# --- MONGODB BAĞLANTISI ---
users_col = None
bans_col = None

if MONGO_URI:
    try:
        db_client = pymongo.MongoClient(MONGO_URI)
        db = db_client.get_database("onay_paylasim_botu")
        users_col = db["aboneler"]
        bans_col = db["yasaklananlar"]
        print("MongoDB bağlantısı başarılı.")
    except Exception as e:
        print(f"MongoDB bağlantı hatası: {e}")
else:
    print("UYARI: MONGO_URI çevresel değişkeni tanımlanmamış!")

processed_albums = set()

# --- SESSİZ KAYIT SİSTEMİ ---
def kullanici_kaydet(user_id):
    if not user_id or users_col is None:
        return
    try:
        uid = int(user_id)
        if uid > 0:
            users_col.update_one({"user_id": uid}, {"$set": {"user_id": uid, "last_active": datetime.datetime.now(datetime.timezone.utc)}}, upsert=True)
    except Exception as e:
        print(f"Kullanıcı kaydetme hatası: {e}")

# --- KANAL ÜYELİK KONTROLÜ (FORCE CHANNEL JOIN) ---
def check_user_membership(user_id):
    """Kullanıcının TARGET_CHANNEL_ID kanalına katılıp katılmadığını kontrol eder."""
    if not TARGET_CHANNEL_ID or not bot:
        return True
    if user_id == PATRON_ID:
        return True
    try:
        member = bot.get_chat_member(chat_id=TARGET_CHANNEL_ID, user_id=user_id)
        # creator, administrator, member, restricted durumları onaylı kabul edilir
        if member.status in ['creator', 'administrator', 'member', 'restricted']:
            return True
        return False
    except Exception as e:
        print(f"Kanal üyelik kontrolü uyarısı: {e}")
        # Bot kanalda yönetici değilse veya API geçici hata verirse
        return False

def get_channel_join_markup():
    markup = InlineKeyboardMarkup()
    if CHANNEL_INVITE_LINK:
        btn_join = InlineKeyboardButton("📢 Kanala Katıl", url=CHANNEL_INVITE_LINK)
        markup.add(btn_join)
    elif CHANNEL_USERNAME:
        btn_join = InlineKeyboardButton("📢 Kanala Katıl", url=f"https://t.me/{CHANNEL_USERNAME}")
        markup.add(btn_join)
    btn_check = InlineKeyboardButton("✅ Katıldım / Kontrol Et", callback_data="check_channel_join")
    markup.add(btn_check)
    return markup

# --- TOPLU MESAJ MOTORU ---
def toplu_mesaj_gonder(metin):
    if users_col is None or not bot:
        return 0, 0
    aboneler = users_col.find({})
    basarili = 0
    engellemis = 0
    for abo in aboneler:
        u_id = abo.get("user_id")
        if not u_id:
            continue
        try:
            bot.send_message(u_id, metin, parse_mode="HTML")
            basarili += 1
            time.sleep(0.05)
        except Exception as e:
            if "blocked" in str(e) or "deactivated" in str(e) or "chat not found" in str(e):
                users_col.delete_one({"user_id": u_id})
                engellemis += 1
    print(f"📢 Yayın Raporu -> Başarılı: {basarili} | Engelleyenler: {engellemis}")
    return basarili, engellemis

# --- KOMUTLAR ---

@bot.message_handler(commands=['start'], chat_types=['private'])
def send_welcome(message):
    kullanici_kaydet(message.from_user.id)
    user_id = message.from_user.id

    if bans_col is not None and bans_col.find_one({"user_id": user_id}):
        try:
            bot.reply_to(message, "🚫 Bot kullanımınız engellenmiştir.")
        except:
            pass
        return

    welcome_text = (
        "🤫 <b>Anonim İtiraf Botuna Hoş Geldiniz!</b>\n\n"
        "İçinizde tutamadığınız, kimseyle paylaşamadığınız her şeyi buraya özgürce yazabilir, fotoğraf veya video gönderebilirsiniz.\n\n"
        "🔒 <b>Tamamen Anonim:</b> Gönderdiğiniz itiraflar kanalımızda <b>isminiz, kullanıcı adınız veya profiliniz kesinlikle görünmeden</b> tamamen anonim olarak paylaşılır.\n\n"
        "📩 İtirafınız yöneticilerimiz tarafından incelendikten sonra onaylanırsa resmi kanalımızda yayınlanır.\n\n"
        "⚠️ <b>Kural:</b> İtiraf gönderebilmek için resmi kanalımıza katılmış olmanız gerekmektedir."
    )
    
    # Kanal üyeliği kontrolü
    if not check_user_membership(user_id):
        welcome_text += "\n\n❗ <b>İtiraf gönderebilmek için lütfen önce aşağıdaki kanala katılın:</b>"
        try:
            bot.reply_to(message, welcome_text, parse_mode="HTML", reply_markup=get_channel_join_markup())
        except:
            pass
        return

    try:
        bot.reply_to(message, welcome_text, parse_mode="HTML")
    except:
        pass

@bot.message_handler(commands=['mesaj'])
def admin_manuel_mesaj(message):
    if message.chat.id != ADMIN_GROUP_ID and message.from_user.id != PATRON_ID:
        return
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Metin girmeyi unuttunuz!\n\n<b>Kullanım:</b> <code>/mesaj İletilecek Mesaj Metni</code>", parse_mode="HTML")
        return
    yayin_metni = parts[1].strip()
    durum = bot.reply_to(message, "⏳ Toplu mesaj yayını başlatıldı, lütfen bekleyiniz...")
    basarili, engellemis = toplu_mesaj_gonder(yayin_metni)
    try:
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=durum.message_id,
            text=f"📢 <b>Yayın Tamamlandı!</b>\n\n✅ Ulaşan: <code>{basarili}</code>\n❌ Silinen/Engelleyen: <code>{engellemis}</code>",
            parse_mode="HTML"
        )
    except:
        pass

@bot.message_handler(commands=['unban'])
def unban_user(message):
    if message.chat.id != ADMIN_GROUP_ID and message.from_user.id != PATRON_ID:
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ <b>Kullanım:</b> <code>/unban user_id</code>", parse_mode="HTML")
        return
    try:
        user_id = int(parts[1])
        if bans_col is not None:
            sonuc = bans_col.delete_one({"user_id": user_id})
            if sonuc.deleted_count > 0:
                bot.reply_to(message, f"✅ <b>{user_id}</b> ID'li kullanıcının yasağı kaldırıldı.", parse_mode="HTML")
            else:
                bot.reply_to(message, "❌ Bu ID'ye ait yasaklama kaydı bulunamadı.", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message, "⚠️ Geçersiz kullanıcı ID'si!", parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"Hata: {e}")

@bot.message_handler(commands=['stats'])
def bot_stats(message):
    if message.chat.id != ADMIN_GROUP_ID and message.from_user.id != PATRON_ID:
        return
    user_count = users_col.count_documents({}) if users_col is not None else 0
    ban_count = bans_col.count_documents({}) if bans_col is not None else 0
    text = (
        f"📊 <b>İtiraf Botu İstatistikleri</b>\n\n"
        f"👥 Kayıtlı Kullanıcı Sayısı: <code>{user_count}</code>\n"
        f"🚫 Yasaklı Kullanıcı Sayısı: <code>{ban_count}</code>"
    )
    try:
        bot.reply_to(message, text, parse_mode="HTML")
    except:
        pass

# --- KANAL KATILIM KONTROL BUTONU CALLBACK'İ ---
@bot.callback_query_handler(func=lambda call: call.data == "check_channel_join")
def handle_channel_join_check(call):
    user_id = call.from_user.id
    if check_user_membership(user_id):
        bot.answer_callback_query(call.id, "🎉 Katılımınız onaylandı!")
        try:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=(
                    "✅ <b>Katılımınız Onaylandı!</b>\n\n"
                    "Artık kanalımızda anonim olarak paylaşılmasını istediğiniz <b>itirafınızı (metin, fotoğraf veya video)</b> doğrudan buraya gönderebilirsiniz 🤫\n\n"
                    "Yöneticilerimiz inceleyip onayladıktan sonra kanalımızda <b>kimliğiniz gizli tutularak</b> paylaşılacaktır."
                ),
                parse_mode="HTML"
            )
        except:
            pass
    else:
        bot.answer_callback_query(call.id, "⚠️ Henüz kanala katılmadınız! Lütfen önce kanala katılın.", show_alert=True)

# --- KULLANICI GÖNDERİ YAKALAYICISI (METİN, FOTOĞRAF, VİDEO) ---
@bot.message_handler(content_types=['text', 'photo', 'video', 'document', 'voice'], chat_types=['private'])
def handle_user_submission(message):
    user_id = message.from_user.id
    kullanici_kaydet(user_id)

    # Komut ise işleme
    if message.text and message.text.startswith('/'):
        return

    # Ban kontrolü
    if bans_col is not None and bans_col.find_one({"user_id": user_id}):
        try:
            bot.reply_to(message, "🚫 Bot kullanımınız yasaklanmıştır.")
        except:
            pass
        return

    # Kanal Üyelik Kontrolü
    if not check_user_membership(user_id):
        warning_text = (
            "📢 <b>İtiraf Gönderebilmek İçin Kanala Katılmalısınız!</b>\n\n"
            "İtirafınızın incelenmesi ve kanalımızda anonim olarak paylaşılabilmesi için resmi kanalımıza katılmanız gerekmektedir.\n\n"
            "Aşağıdaki butondan kanala katıldıktan sonra <b>'✅ Katıldım / Kontrol Et'</b> butonuna basınız."
        )
        try:
            bot.reply_to(message, warning_text, parse_mode="HTML", reply_markup=get_channel_join_markup())
        except:
            pass
        return

    # Albüm kontrolü
    if message.media_group_id:
        if message.media_group_id not in processed_albums:
            processed_albums.add(message.media_group_id)
            try:
                bot.reply_to(message, "⚠️ Lütfen medyaları albüm olarak değil, tek tek gönderiniz.")
            except:
                pass
        return

    orig_msg_id = message.message_id
    user_name = str(message.from_user.first_name).replace("<", "").replace(">", "")
    user_link = f"@{message.from_user.username}" if message.from_user.username else f'<a href="tg://user?id={user_id}">{user_name}</a>'
    
    # İçerik metni / caption
    content_caption = message.caption if message.caption else (message.text if message.text else "")
    
    # Onay grubuna gidecek butonlar
    markup = InlineKeyboardMarkup()
    btn_approve = InlineKeyboardButton("Onayla ✅", callback_data=f"app_{user_id}_{orig_msg_id}")
    btn_reject = InlineKeyboardButton("Reddet ❌", callback_data=f"rej_{user_id}_{orig_msg_id}")
    btn_ban = InlineKeyboardButton("Kullanıcıyı Banla 🚫", callback_data=f"ban_{user_id}_{orig_msg_id}")
    markup.add(btn_approve, btn_reject)
    markup.add(btn_ban)

    admin_header = f"🤫 <b>YENİ İTİRAF GELDİ!</b>\n\n👤 <b>Gönderen:</b> {user_link} (ID: <code>{user_id}</code>)\n"
    if content_caption:
        admin_header += f"\n📝 <b>İtiraf:</b>\n{content_caption}"
    else:
        admin_header += "\n<i>(Metin/Açıklama girilmedi)</i>"

    try:
        if message.content_type == 'photo':
            bot.send_photo(ADMIN_GROUP_ID, message.photo[-1].file_id, caption=admin_header, reply_markup=markup, parse_mode='HTML')
        elif message.content_type == 'video':
            bot.send_video(ADMIN_GROUP_ID, message.video.file_id, caption=admin_header, reply_markup=markup, parse_mode='HTML')
        elif message.content_type == 'text':
            bot.send_message(ADMIN_GROUP_ID, text=admin_header, reply_markup=markup, parse_mode='HTML')
        elif message.content_type == 'document':
            bot.send_document(ADMIN_GROUP_ID, message.document.file_id, caption=admin_header, reply_markup=markup, parse_mode='HTML')
        elif message.content_type == 'voice':
            bot.send_voice(ADMIN_GROUP_ID, message.voice.file_id, caption=admin_header, reply_markup=markup, parse_mode='HTML')

        bot.reply_to(message, "🤫 <b>İtirafınız alındı!</b>\n\nYöneticilerimiz tarafından incelendikten sonra uygun görülürse kanalımızda <b>tamamen anonim</b> olarak paylaşılacaktır.", parse_mode="HTML")
    except Exception as e:
        print(f"Onay grubuna iletme hatası: {e}")
        bot.reply_to(message, "⚠️ İtirafınız iletilirken bir hata oluştu. Lütfen daha sonra tekrar deneyiniz.")

# --- YÖNETİCİ ONAY / RED / BAN İŞLEYİCİSİ ---
@bot.callback_query_handler(func=lambda call: call.data.startswith(("app_", "rej_", "ban_")))
def handle_admin_action(call):
    if call.message.chat.id != ADMIN_GROUP_ID and call.from_user.id != PATRON_ID:
        bot.answer_callback_query(call.id, "Bu işlemi sadece yöneticiler yapabilir!", show_alert=True)
        return

    parts = call.data.split("_")
    action = parts[0]
    user_id = int(parts[1])
    orig_msg_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None

    admin_msg = call.message
    admin_isim = str(call.from_user.first_name).replace('<', '').replace('>', '')
    admin_etiket = f'<a href="tg://user?id={call.from_user.id}">{admin_isim}</a>'

    full_caption = admin_msg.caption if admin_msg.caption else (admin_msg.text if admin_msg.text else "")
    
    # Kanalda yayınlanacak metni hazırla (Admin başlığını ayıkla)
    channel_raw = ""
    if "📝 <b>İtiraf:</b>\n" in full_caption:
        channel_raw = full_caption.split("📝 <b>İtiraf:</b>\n", 1)[1].strip()
    elif "(Metin/Açıklama girilmedi)" not in full_caption and "📝 <b>İtiraf:</b>" in full_caption:
        channel_raw = full_caption.split("📝 <b>İtiraf:</b>", 1)[1].strip()
    elif "📝 <b>İçerik/Açıklama:</b>\n" in full_caption:
        channel_raw = full_caption.split("📝 <b>İçerik/Açıklama:</b>\n", 1)[1].strip()

    # Botun kullanıcı adını al
    bot_uname = get_bot_username()
    bot_tag = f"@{bot_uname}" if bot_uname else ""

    # Şık ve modern ayırıcı formatı: İtiraf + Estetik Çizgi + İtiraf için @bot_adi
    footer = "✦ ────────────────────── ✦\n"
    if bot_tag:
        footer += f"🤫 <b>İtiraf için:</b> {bot_tag}"
    else:
        footer += "🤫 <b>İtiraf göndermek için bota yazabilirsiniz.</b>"

    if channel_raw:
        channel_text = f"{channel_raw}\n\n{footer}"
    else:
        channel_text = footer

    if action == "app":
        try:
            sent_channel_msg = None
            if admin_msg.content_type == 'photo':
                sent_channel_msg = bot.send_photo(TARGET_CHANNEL_ID, admin_msg.photo[-1].file_id, caption=channel_text, parse_mode='HTML')
                if BACKUP_CHANNEL_ID:
                    try: bot.send_photo(BACKUP_CHANNEL_ID, admin_msg.photo[-1].file_id, caption=channel_text, parse_mode='HTML')
                    except: pass
            elif admin_msg.content_type == 'video':
                sent_channel_msg = bot.send_video(TARGET_CHANNEL_ID, admin_msg.video.file_id, caption=channel_text, parse_mode='HTML')
                if BACKUP_CHANNEL_ID:
                    try: bot.send_video(BACKUP_CHANNEL_ID, admin_msg.video.file_id, caption=channel_text, parse_mode='HTML')
                    except: pass
            elif admin_msg.content_type == 'text':
                sent_channel_msg = bot.send_message(TARGET_CHANNEL_ID, text=channel_text, parse_mode='HTML')
                if BACKUP_CHANNEL_ID:
                    try: bot.send_message(BACKUP_CHANNEL_ID, text=channel_text, parse_mode='HTML')
                    except: pass
            elif admin_msg.content_type == 'document':
                sent_channel_msg = bot.send_document(TARGET_CHANNEL_ID, admin_msg.document.file_id, caption=channel_text, parse_mode='HTML')
            elif admin_msg.content_type == 'voice':
                sent_channel_msg = bot.send_voice(TARGET_CHANNEL_ID, admin_msg.voice.file_id, caption=channel_text, parse_mode='HTML')

            post_link = ""
            if sent_channel_msg:
                if CHANNEL_USERNAME:
                    post_link = f"https://t.me/{CHANNEL_USERNAME}/{sent_channel_msg.message_id}"
                elif str(TARGET_CHANNEL_ID).startswith("-100"):
                    raw_id = str(TARGET_CHANNEL_ID)[4:]
                    post_link = f"https://t.me/c/{raw_id}/{sent_channel_msg.message_id}"

            # Admin mesajını güncelle
            new_admin_text = f"✅ {admin_etiket} Tarafından ONAYLANDI\n\n{full_caption}"
            if len(new_admin_text) > 1024:
                new_admin_text = new_admin_text[:1020] + "..."

            try:
                if admin_msg.content_type in ['photo', 'video', 'document', 'voice']:
                    bot.edit_message_caption(new_admin_text, chat_id=admin_msg.chat.id, message_id=admin_msg.message_id, reply_markup=None, parse_mode='HTML')
                else:
                    bot.edit_message_text(new_admin_text, chat_id=admin_msg.chat.id, message_id=admin_msg.message_id, reply_markup=None, parse_mode='HTML')
            except:
                try: bot.edit_message_reply_markup(chat_id=admin_msg.chat.id, message_id=admin_msg.message_id, reply_markup=None)
                except: pass

            # Kullanıcıya bildirim gönder
            try:
                notify_text = "🎉 <b>İtirafınız onaylandı ve kanalımızda anonim olarak paylaşıldı!</b>"
                if post_link:
                    notify_text += f"\n\n🔗 <b>İtirafı Görüntüle:</b> {post_link}"
                if orig_msg_id:
                    bot.send_message(user_id, notify_text, reply_to_message_id=orig_msg_id, parse_mode="HTML")
                else:
                    bot.send_message(user_id, notify_text, parse_mode="HTML")
            except Exception as notify_err:
                print(f"Kullanıcıya bildirim gönderilemedi: {notify_err}")

            bot.answer_callback_query(call.id, "İtiraf onaylandı ve kanalda paylaşıldı!")
        except Exception as e:
            print(f"Onaylama hatası: {e}")
            bot.answer_callback_query(call.id, f"Hata: {str(e)[:50]}")

    elif action == "rej":
        try:
            new_admin_text = f"❌ {admin_etiket} Tarafından REDDEDİLDİ\n\n{full_caption}"
            if len(new_admin_text) > 1024:
                new_admin_text = new_admin_text[:1020] + "..."

            try:
                if admin_msg.content_type in ['photo', 'video', 'document', 'voice']:
                    bot.edit_message_caption(new_admin_text, chat_id=admin_msg.chat.id, message_id=admin_msg.message_id, reply_markup=None, parse_mode='HTML')
                else:
                    bot.edit_message_text(new_admin_text, chat_id=admin_msg.chat.id, message_id=admin_msg.message_id, reply_markup=None, parse_mode='HTML')
            except:
                try: bot.edit_message_reply_markup(chat_id=admin_msg.chat.id, message_id=admin_msg.message_id, reply_markup=None)
                except: pass

            try:
                reject_text = "❌ Gönderdiğiniz itiraf yöneticilerimiz tarafından uygun görülmediği için reddedildi."
                if orig_msg_id:
                    bot.send_message(user_id, reject_text, reply_to_message_id=orig_msg_id)
                else:
                    bot.send_message(user_id, reject_text)
            except:
                pass

            bot.answer_callback_query(call.id, "İtiraf reddedildi.")
        except Exception as e:
            bot.answer_callback_query(call.id, f"Hata: {str(e)[:50]}")

    elif action == "ban":
        if user_id == PATRON_ID:
            bot.answer_callback_query(call.id, "Patron banlanamaz!", show_alert=True)
            return

        if bans_col is not None:
            bans_col.update_one({"user_id": user_id}, {"$set": {"user_id": user_id, "banned_at": datetime.datetime.now(datetime.timezone.utc)}}, upsert=True)

        new_admin_text = f"🚫 {admin_etiket} Tarafından BANLANDI (Kullanıcı Yasaklandı)\n\n{full_caption}"
        if len(new_admin_text) > 1024:
            new_admin_text = new_admin_text[:1020] + "..."

        try:
            if admin_msg.content_type in ['photo', 'video', 'document', 'voice']:
                bot.edit_message_caption(new_admin_text, chat_id=admin_msg.chat.id, message_id=admin_msg.message_id, reply_markup=None, parse_mode='HTML')
            else:
                bot.edit_message_text(new_admin_text, chat_id=admin_msg.chat.id, message_id=admin_msg.message_id, reply_markup=None, parse_mode='HTML')
        except:
            try: bot.edit_message_reply_markup(chat_id=admin_msg.chat.id, message_id=admin_msg.message_id, reply_markup=None)
            except: pass

        try:
            bot.send_message(user_id, "🚫 Bot kullanım kurallarını ihlal ettiğiniz gerekçesiyle yasaklandınız.")
        except:
            pass

        bot.answer_callback_query(call.id, "Kullanıcı banlandı.", show_alert=True)

# --- RENDER & UPTIMEROBOT İÇİN WEB SUNUCUSU ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Anonim İtiraf Botu Aktif ve Çalışıyor! (Render / UptimeRobot)"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, use_reloader=False)

def shutdown_handler(signum, frame):
    print("Kapatma sinyali alındı (SIGTERM/SIGINT). Polling durduruluyor...")
    if bot:
        try:
            bot.stop_polling()
        except Exception:
            pass
    os._exit(0)

signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

if __name__ == "__main__":
    # Render / UptimeRobot için Web Server
    Thread(target=run, daemon=True).start()
    print("Web sunucusu arka planda başlatıldı.")

    if bot:
        # Varsa eski webhook'u sil ve bekleyen eski güncellemeleri temizle
        try:
            bot.delete_webhook(drop_pending_updates=True)
            time.sleep(1)
            print("Webhook temizlendi, polling moduna geçildi.")
        except Exception as e:
            print(f"Webhook temizleme uyarısı: {e}")

        print("Bot dinlemeye başladı (infinity_polling)...")
        while True:
            try:
                bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=20)
            except Exception as e:
                print(f"Polling bağlantı uyarısı: {e}. 5 saniye içinde yeniden bağlanılıyor...")
                time.sleep(5)
    else:
        print("Bot başlatılamadı: BOT_TOKEN eksik.")
