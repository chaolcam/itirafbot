# Kanal Onay & Paylaşım Botu (Render & UptimeRobot Uyumlu)

Bu bot; kullanıcıların gönderdiği **metin, fotoğraf ve videoları** yönetici onay grubuna ileten, onaylandığında hedef kanalda yayınlayan ve **Kanal ID tabanlı Zorunlu Kanal Katılımı (Force Channel Join)** sağlayan bağımsız bir Telegram botudur.

---

## Özellikler
1. **İçerik Desteği:** Düz metin, fotoğraf (başlıklı/başlıksız), video, ses ve belge desteği.
2. **Kanal ID ile Zorunlu Katılım:**
   - Kullanıcı bota içerik gönderdiğinde `TARGET_CHANNEL_ID` kanalına üye olup olmadığı kontrol edilir.
   - Üye değilse gönderi onay grubuna iletilmez, önüne `[📢 Kanala Katıl]` ve `[✅ Katıldım]` butonları gelir.
   - Katılınca veya butona basıp doğrulayınca gönderisini iletebilir.
3. **Yönetici Onay Grubu (`ADMIN_GROUP_ID`):**
   - `[ Onayla ✅ ]`: Gönderiyi hedef kanalda (`TARGET_CHANNEL_ID`) paylaşır ve kullanıcıya bildirim yollar.
   - `[ Reddet ❌ ]`: Gönderiyi reddeder ve kullanıcıya red bildirimi gönderir.
   - `[ Kullanıcıyı Banla 🚫 ]`: Kullanıcıyı veritabanında yasaklar.
4. **Render & UptimeRobot Desteği:**
   - Arka planda Flask tabanlı bir web sunucusu (`PORT: 8080`) çalışır.
   - UptimeRobot üzerinden Render URL'inize (`https://uygulama-adiniz.onrender.com/`) HTTP 200 pingi atarak 7/24 uykusuz çalıştırabilirsiniz.

---

## Render'da Kurulum Adımları
1. Render.com üzerinde **New Web Service** (veya Background Worker) oluşturun.
2. Bu `onay_botu` klasörünü GitHub/GitLab reponuzdan bağlayın.
3. **Build Command:** `pip install -r requirements.txt`
4. **Start Command:** `python bot.py`
5. **Environment Variables (Çevre Değişkenleri):**
   - `BOT_TOKEN`: BotFather'dan aldığınız token.
   - `MONGO_URI`: MongoDB Atlas bağlantı URL'iniz.
   - `ADMIN_GROUP_ID`: Yönetici grubunuzun ID'si (Örn: `-100...`).
   - `TARGET_CHANNEL_ID`: Paylaşımın yapılacağı kanalın ID'si (Örn: `-100...`).
   - `CHANNEL_USERNAME`: Kanal kullanıcı adınız (@ olmadan, opsiyonel).
   - `CHANNEL_INVITE_LINK`: Zorunlu katılım butonu için kanal linki/davet linki.
   - `PATRON_ID`: Telegram kullanıcı ID'niz.
   - `PORT`: `8080` (Render genelde otomatik atar).
