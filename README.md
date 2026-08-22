# Todoist Gemini Bridge 🌉

Bir yapay zeka sohbetinden (Gemini, ChatGPT vb.) veya otomasyon aracından üretilen yapılandırılmış JSON görev çıktılarını Todoist API üzerinden tek seferde, doğru projelere ve tarihlere otomatik eşleyerek ekleyen Python köprüsü.

---

## 🚀 Özellikler

- **Pydantic ile Güçlü Tip ve Şema Doğrulama:** Gelen görev JSON verisini doğrular, eksik veya hatalı alanları yakalar.
- **Markdown & JSON Ayrıştırma:** LLM çıktılarındaki markdown formatlı kod bloklarını (````json ... ````) otomatik ayıklar.
- **Akıllı Proje Eşleştirme:** Görevdeki `project_name` değerini Todoist'teki projelerinizle otomatik eşleştirip `project_id` değerini bulur. Bulunamazsa görevi güvenle `Inbox`'a yönlendirir.
- **Güncel Todoist API v1 Desteği:** En güncel Todoist API (`https://api.todoist.com/api/v1`) uç noktalarıyla tam uyumlu.
- **Renkli Konsol Özeti ve Görev Linkleri:** Eklenen görevlerin doğrudan Todoist web linklerini ve özetini terminalde renkli tablo halinde gösterir.

---

## 📦 Kurulum

### 1. Depoyu Klonlayın
```bash
git clone https://github.com/kagankurubas/Todoist-Gemini-Bridge.git
cd Todoist-Gemini-Bridge
```

### 2. Sanal Ortam Oluşturun ve Paketleri Yükleyin
```bash
python -m venv venv

# Windows:
venv\Scripts\activate

# macOS / Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Çevre Değişkenlerini Ayarlayın
`.env.example` dosyasını `.env` olarak kopyalayın ve Todoist API tokenınızı ekleyin:
```bash
cp .env.example .env
```
`.env` içeriği:
```env
TODOIST_API_TOKEN=your_todoist_api_token_here
```
> **Not:** Todoist API Tokenınızı [Todoist Ayarlar > Geliştirici](https://todoist.com/app/settings/integrations/developer) sayfasından alabilirsiniz.

---

## 🛠️ Kullanım

### 1. JSON Dosyasından Görev Ekleme
```bash
python main.py --file tasks.json
```

### 2. Doğrudan JSON Metni ile Çalıştırma
```bash
python main.py --json '[{"content": "Toplantı Notlarını Hazırla", "due_string": "tomorrow at 10:00", "priority": 3}]'
```

### 3. İnteraktif Mod (Konsola Yapıştırarak)
Parametresiz çalıştırıp doğrudan JSON metnini terminale yapıştırabilirsiniz:
```bash
python main.py
```

---

## 📋 Örnek JSON Şeması

```json
[
  {
    "content": "ESP32 Devre Şeması İncelemesi",
    "project_name": "Odak & Gelişim",
    "due_string": "today at 18:00",
    "priority": 3,
    "description": "DHT22 pinout bağlantıları kontrol edilecek"
  },
  {
    "content": "Haftalık Bülten Oku",
    "project_name": "Odak & Gelişim",
    "due_string": "Friday",
    "priority": 2
  }
]
```

---

## 📄 Lisans

Bu proje [MIT Lisansı](LICENSE) ile lisanslanmıştır.
