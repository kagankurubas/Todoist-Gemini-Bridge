# CLAUDE.md

Bu dosya, Claude Code'a (claude.ai/code) bu repoda çalışırken rehberlik eder.

## Komutlar

```bash
# Mevcut venv'i etkinleştir (Windows)
.\venv\Scripts\activate

# Bağımlılıkları kur
pip install -r requirements.txt

# Tüm test paketini çalıştır (132 test)
pytest
pytest -v

# Tek bir test dosyası / testi çalıştır
pytest tests/test_mcp.py
pytest tests/test_mcp.py::test_create_task_resolves_project -v

# FastAPI webhook sunucusunu çalıştır (app.py)
uvicorn app:app --port 8000
# Swagger UI: http://127.0.0.1:8000/docs

# MCP sunucusunu doğrudan çalıştır (normalde Claude Desktop tarafından STDIO üzerinden başlatılır)
python todoist_mcp.py

# Bağımsız CLI ile görev oluşturma (main.py)
python main.py --file tasks_sample.json
python main.py --json '[{"content": "Task", "due_string": "today", "priority": 2}]'

# Google Tasks -> Todoist senkronizasyon servisi
python sync_worker.py                    # tek seferlik
python sync_worker.py --watch --interval 15   # sürekli izleme (polling)

# Webhook istemcisi (bir JSON dosyasını çalışan app.py örneğine gönderir)
python send_to_bridge.py --file tasks_sample.json

# Docker (varsayılan olarak sync_worker.py'yi tek seferlik çalıştırır)
docker build -t todoist-bridge .
docker run --env-file .env todoist-bridge
```

Bu repoda yapılandırılmış bir linter/formatter yok (ruff/black/mypy config yok) — böyle bir şey varmış gibi davranma.

Gerekli ortam değişkenleri (`.env`, bkz. `.env.example`): `TODOIST_API_TOKEN`, `WEBHOOK_SECRET_TOKEN`, opsiyonel `ALLOWED_ORIGINS` (CORS, varsayılan `*`). `config.py` içindeki Pydantic `Settings` üzerinden yüklenir. Sync worker ayrıca repo kökünde bir Google OAuth `credentials.json` (Desktop Client) dosyasına ihtiyaç duyar; `token.json` ilk kimlik doğrulamada otomatik oluşturulur. Sunucusuz/geçici (serverless/ephemeral) ortamlar için ikisi de `GOOGLE_CREDENTIALS_JSON` / `GOOGLE_TOKEN_JSON` ortam değişkenlerinden sağlanabilir.

## Mimari

Bu proje tek bir uygulama değil, **hepsi aynı doğrulama/görev-oluşturma çekirdeğinden geçen dört bağımsız giriş noktasından** oluşan bir Python araç setidir:

- `todoist_mcp.py` — Claude Desktop'a sunulan araç yüzeyi; STDIO üzerinden çalışan FastMCP sunucusu. Kendi kendine yeterlidir: Todoist ile `todoist_client.py` üzerinden değil, doğrudan resmi `todoist-api-python` SDK'sı üzerinden konuşur ve kendi isim çözümleme/doğrulama mantığına sahiptir.
- `app.py` — FastAPI REST sunucusu (n8n/Make gibi otomasyonlar için webhook hedefi). Kimlik doğrulama, sabit-zamanlı (`secrets.compare_digest`) `X-Bridge-Token` header karşılaştırmasıyla yapılır.
- `main.py` — doğrudan çalıştırılan CLI aracı; ayrıca `build_project_map` / `resolve_project_id` fonksiyonlarını export eder ve bunlar `app.py` tarafından kendi proje-adı çözümlemesi için import edilip yeniden kullanılır.
- `sync_worker.py` — Google Tasks'ten görev çeken, her öğeyi `parse_google_task` ile dönüştüren, Todoist'e gönderen ve başarılı olan görevleri kaynak Google Task'ten silen OAuth 2.0 servisi.

### Paylaşılan çekirdek (`main.py`, `app.py`, `sync_worker.py` tarafından kullanılır)

- `models.py` — `TaskPayload` (tekil görev) ve `BatchTaskPayload` (`tasks: List[TaskPayload]`, maksimum 50) her şeyin doğrulandığı Pydantic şemalarıdır. `project_name` varsayılan olarak `"Odak & Gelişim"`dir; `priority` 1 (normal) ile 4 (acil) arasındadır — dikkat: Todoist'in kendi API'si ve `sync_worker.py`'nin etiket ayrıştırıcısı (`p1`=acil..`p4`=normal) bu skalayı tersine çevirir, bu nedenle öncelik eşlemesi `parse_google_task` içinde açıkça yapılır.
- `parser.py` — `parse_tasks_from_json`, ham LLM çıktısındaki markdown kod bloklarını (` ```json ... ``` `) temizler, ardından üç JSON biçimini kabul eder: düz bir liste, `{"tasks": [...]}` ya da tekil bir görev objesi. Hata durumunda `TaskParseError` fırlatır.
- `todoist_client.py` — Todoist REST API v1 üzerine ince bir `requests` sarmalayıcısı (`main.py`, `app.py`, `sync_worker.py` tarafından kullanılır; `todoist_mcp.py` tarafından KULLANILMAZ, o SDK kullanır). `app.py`'nin FastAPI exception handler'ları aracılığıyla HTTP yanıtlarına eşlediği tipli exception'lar fırlatır (`TodoistAuthError` 401, `TodoistValidationError` 400, `TodoistServerError` 5xx, temel sınıf olarak `TodoistAPIError`). `create_task`, ilk pozisyonel argüman olarak hem keyword argümanları hem de bir `TaskPayload`/dict kabul eder.
- Proje-adı çözümlemesi, aynı case-insensitive/Unicode-normalize edilmiş mantıkla bilinçli olarak üç farklı yerde tekrarlanır: `main.py::resolve_project_id` (dict lookup), `todoist_client.py::resolve_project_name` (Todoist REST), ve `todoist_mcp.py::_resolve_project` (SDK, ek olarak Inbox-alias ve kısmi eşleşme katmanlarıyla). Çözümleme mantığına dokunurken değişikliğin her üçüne de uygulanması gerekip gerekmediğini kontrol et.

### `todoist_mcp.py` iç yapısı

Repodaki en büyük dosya (~1400 satır); her Todoist işlemi (görevler, bölümler, etiketler, yorumlar, iç içe/parent_id hiyerarşili projeler dahil) için bir `@mcp.tool()` dekoratörlü fonksiyon vardır. Her araç bağımsız olarak:
1. Girdileri dosyanın başında tanımlı `MAX_*_LENGTH` sabitlerine göre doğrular.
2. İnsan tarafından okunabilir isimleri `_resolve_project` / `_resolve_label` / `_resolve_section` yardımcı fonksiyonlarıyla ID'lere çözümler (ID eşleşmesi → tam isim eşleşmesi → kısmi eşleşme, `_normalize` ile Türkçe'ye duyarlı normalizasyon dahil).
3. Todoist SDK'sını çağırır (`TodoistAPI`, her çağrıda `_get_api_client()` tarafından `TODOIST_API_TOKEN`'dan oluşturulur).

### `sync_worker.py` etiket sözdizimi

`parse_google_task`, serbest metin Google Task başlıklarından/notlarından regex ile yapılandırılmış alanları şu sırayla çıkarır: öncelik (`p[1-4]`), teslim tarihi (`@today`, `@tomorrow at 15:00`, ...), proje (`[Proje Adı]` veya `#Proje Adı`), ardından notlardan çekilen ve Google'ın `due` tarihiyle birleştirilip ISO `due_datetime` haline getirilen satır içi bir saat (`Saat: HH:MM` veya çıplak `HH:MM`). Etiket çıkarımından sonra kalan metin `content` olur.

### Testler

`tests/` modül yapısını birebir yansıtır (`test_mcp.py`, `test_api.py`, `test_models.py`, `test_parser.py`, `test_todoist_client.py`, `test_project_resolution.py`) ve tüm ağ/API çağrılarını mock'lar — gerçek bir Todoist veya Google çağrısı yapılmaz. `test_mcp.py`, SDK client'ını topyekûn mock'lamak yerine SDK'nın obje özniteliklerini yansıtan hafif `MockProject`/`MockLabel`/`MockSection` sınıfları tanımlar.
