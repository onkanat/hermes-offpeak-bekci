# Değişiklik Günlüğü — offpeak-bekci

Sürüm numarasının TEK beyan kaynağı `plugin.yaml` → `version` alanıdır
(`plugin-catalog/offpeak-bekci.yaml` → `version` onunla aynı olmak zorundadır).

## [0.1.2] — 2026-10-16

- **`ozet` yanıltıcıydı, düzeltildi:** "kuyruk 4 bekliyor / 3 onaylı" yazıyordu ama o 4 kalem **koşulmuştu**
  (`bekleyen` alanı geriye uyumluluk için "onaysız"ı sayıyor, koşulmuşları da içeriyordu). Artık özet
  **toplam · onaylı · koşuldu** yazar; gerçekten iş bekleyen varsa `· N onay/sahipsiz bekliyor` eklenir.
- `kuyruk` alanına **`onay_bekleyen`** eklendi (= toplam − onaylı − koşuldu − atlandı); `bekleyen` alanı
  uyumluluk için yerinde kaldı, anlamı docstring'de yazılı. Kapı: `tests/test_komut_cikti.py` sayaç testi.

## [0.1.1] — 2026-10-16

- `/offpeak-durum` artık **okunur rapor** döner (varsayılan); makine çıktısı `json` argümanına taşındı
  (`/offpeak-durum json`). Sebep: kullanıcı komutu kendisi yazdığında ham JSON **okunamıyordu**
  (ölçüm: masaüstü sohbeti, 16.10.2026). Rozet `json` argümanını geçer; JSON **sözleşmesi (anahtarlar)
  değişmedi**, yalnız varsayılan çıktı biçimi değişti.
- Yeni kapı: `tests/test_komut_cikti.py` — rapor insan okur ve kısa (≤14 satır), `json` argümanı
  sözleşmeyi koruyor, okunamayan kuyruk defteri raporda görünür.
- README: masaüstü yarısının kurulum satırı ve `json` argümanı belgelendi.

## [0.1.0] — 2026-10-16

İlk sürüm. Bugüne kadarki dilimler (W1…W5), her biri tek satır:

- **W1** (16.10.2026) — Test kusurları gerekçesiyle düzeltildi (parite şablonu `replace()`, gecikme tavanı formülden 540 sn, kayan pencere yarı açık `(ts-pencere_sn, ts]`); `kuru_kosu` kapısı canlı `config.yaml` ile ölçüldü. Python kapıları yeşil.
- **W2** (16.10.2026) — Masaüstü yarısı `desktop/plugin.js` olarak kuruldu ve rozetin çizildiği izole ölçümle doğrulandı (`tools/build-desktop.mjs --check` EXIT=0); tek satır kurulum `tools/kur.sh` ve katalog girdisi taslağı (`plugin-catalog/`) eklendi.
- **W3** (16.10.2026) — Sunucu yarısı etkinleştirildi: `plugins.enabled` + kuyruk defteri tablo ayrıştırma, masaüstü sayaç/`slash.exec` kimliği ve `llm_execution` (A3) middleware'i canlıda; kurulu kopya ile repo commit'i birebir.
- **W4a** (16.10.2026) — Ayarların tek beyan kaynağı `plugin.yaml` → `config_schema` oldu; etkin değer zinciri `config.yaml:offpeak-bekci` > `ctx.config` > şema varsayılanı olarak şartnameye hizalandı; sunucu tarafı ayarlar ve kuyruk yolu göçü tamamlandı (eklentiye gömülü yol yok).
- **W4a-2** (16.10.2026) — Masaüstü kabuk davranış testi: ayar zinciri ve geçici defter sayıları rozete gerçekten geçiyor mu (canlı config ile 4/0, tek satır değişince 3/1).
- **W4b** (16.10.2026) — Opt-in kurulum komutları `/offpeak-kur` (tam plan + `plan_hash` onayı) ve `/offpeak-kaldir`; host kanalı sınırı (klasik CLI / Ink TUI-masaüstü panel) disclosure'ı ve kural 9 ölçümü; cron deposuna yazma yok (salt-okunur).
- **W5** (16.10.2026) — Yayın hijyeni: `LICENSE` (MIT + `deepseek-whale` türev atfı) ve bu `CHANGELOG.md` eklendi; katalog `sha` pini son içerik commit'ine tazelendi. Kod/test davranışı değişmedi (97 test OK, `hermes plugins validate` EXIT=0).

### Bilinen sınırlar (0.1.0)

- `plugin-catalog/offpeak-bekci.yaml` **taslaktır**: PR açılmadı, repo henüz herkese açık değil (GitHub 404 ölçümü, 16.10.2026) ve checkout'ta `origin` remote'u yok. Yayınlanıncaya kadar geçerli kurulum `tools/kur.sh` (kaynak kurulum).
- Otomatik bırakma host'a bağlıdır: Ink TUI / masaüstü-panel host'unda istek tek satır JSON olarak basılır, işi ajanın cron aracı kurar (bkz. `README.md` → “Hangi host'ta otomatik bırakılır?”).
- `kuru_kosu` varsayılanı `true`: eklenti ölçer, geciktirmez.
