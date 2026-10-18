# Değişiklik Günlüğü — offpeak-bekci

Sürüm numarasının TEK beyan kaynağı `plugin.yaml` → `version` alanıdır
(`plugin-catalog/offpeak-bekci.yaml` → `version` onunla aynı olmak zorundadır).

## [0.1.5] — 2026-10-18

**The desktop chip now follows the `dil` setting.**

- `config.yaml → offpeak-bekci.dil: tr` renders Turkish badge words even inside an English app; `dil: en`
  renders English inside a Turkish app; unset keeps the previous behaviour (application locale).
  Implemented as a pure helper (`rozetDilSec`, `ROZET_DIZGISI`) in the desktop core with
  `tests/desktop/dil.test.mjs` (3 cases). Suites: 7 + 12 + 3 JS, 116 Python — all green.
- No machine-contract change: `/offpeak-durum json` keys and numbers are untouched.

## [0.1.4] — 2026-10-17

**English-first user-facing text (maintainer review of PR #139797), Turkish selectable.**

- New `metinler.py`: a pure catalog of 103 message keys × {`en`, `tr`} plus `dil_sec(ayar)` and
  `t(key, dil, **kw)`. Every user-facing string in `__init__.py` (slash-command descriptions and
  `args_hint`, the `/offpeak-durum` readable report, the outputs of `/offpeak-onayla`,
  `/offpeak-kur`, `/offpeak-kaldir`, notices and error messages) and in `bekci_kurulum.py` (install
  plan, warnings, injected request texts, removal report, runner prompt) now goes through it.
- **English is the default**; set `dil: tr` in `config.yaml` → `offpeak-bekci:` to get the previous
  Turkish wording back (byte-identical to 0.1.3, verified). `bekci_core.py` declares `dil` in the
  settings order and schema defaults.
- `plugin.yaml` description, the catalog entry (`title` / `description`) and `README.md` are
  English-first; Turkish documentation moved to `README.tr.md`.
- Machine contracts unchanged: `/offpeak-durum json` keeps the same keys/types/numbers (the only
  addition is the `dil` key inside the `ayar` block, which `plugin.yaml` already declares). The
  desktop half passes `dil` through (`ORTAK_AYAR_ANAHTARLARI`, `AYAR_TIPLERI`) and was rebuilt.
- Gates: 116 Python tests OK · 7/7 desktop tests (+12 core) · `build-desktop --check` OK ·
  `hermes plugins validate` passed.
- Note: `plan_hash` differs between an English and a Turkish install plan (the prompt is part of
  the hashed fields); jobs installed earlier keep working.

## [0.1.3] — 2026-10-16

**Çalışma zamanı DEĞİŞMEDİ** — bu bir ölçüm/test sürümüdür: `bekci_core.py` (sha256 `5f0c9d0c…`) ve
`desktop/plugin.js` (sha256 `a39fcacb…`) 0.1.2 ile **birebir aynıdır**; 0.1.2 kurulu olan makinede
yeniden kurulum gerekmez, yalnız kayıt/pin tazelenir.

- **Kapı kusuru düzeltildi (makineye bağımlı test):** `tests/test_bekci_core.py` içindeki gerçek-defter
  testi sabit `"K-001"` öneki arıyordu → başka makinede (kendi önek ailesi, ör. `A-*`) **düşüyordu**
  (kurulu ortamda `107 test · FAILED · EXIT=1`), temiz klonda ise defter olmadığı için tamamen **SKIP**
  oluyordu (yani davranış hiç sınanmıyordu). Artık: kimlikler **tek bir önek ailesinden** mi +
  `<önek>-<sayı>` biçiminde mi + `durum` sözlükte mi.
- **Yeni `SentetikDefterTest`** (makineden bağımsız, 2 test): defter içeriği testin içinde üretilir,
  `K-*`/`A-*`/`G-*`/`T-*` önekleri sınanır → temiz klonda da koşar.
- Ortam değişkeni doğru yazımla **`OFFPEAK_KUYRUK_YOLU`** (eski yanlış yazım `KUYRIK` de kabul edilir).
- Katalog girdisi: pin açıklaması 0.1.2'ye güncellendi; `--no-deps` hakkındaki yanlış yönlendirme
  kaldırıldı (`requires_env: []` · `python_dependencies: []` → `--no-deps` gereksizdir ve **aktif bir
  eklentiyi değiştirirken reddedilir**; doğru kurulum `--force --enable`).
- Kapılar: `python3 -m unittest discover -s tests -t .` → **109 test OK** · hijyen kapısı yeşil ·
  `node --test tests/desktop/plugin.test.mjs` → 7/7 · `hermes plugins validate .` → EXIT=0.

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
