# offpeak-bekci (Türkçe belge)

> English documentation: [`README.md`](README.md). Komut çıktıları varsayılan olarak İngilizce'dir;
> `dil: tr` ayarıyla Türkçe'ye döner.

Ollama Cloud'un **off-peak penceresini görünür kılar**: durum çubuğu rozeti pencerenin geri
sayımını ve kuyrukta onay bekleyen/onaylı iş kalemlerini gösterir, pencere açılmadan
`on_bildirim_dk` dakika önce bir kez uyarır, onayı yalnız kullanıcıdan alır. Gövde tarafında
`llm_execution` middleware'i — yalnız Ollama Cloud çağrılarında ve yalnız peak penceresinde —
dakikalık çağrı hızını ölçer; `kuru_kosu: true` iken **hesaplar, uyumaz**.

![Rozet](docs/rozet.png)

Rozet: pencere/geri sayım · `ONAYLI/TOPLAM` sayaç · kota durumu. (Görsel: gerçek masaüstü
çubuğundan kırpılmış, ölçüm anına ait; `docs/rozet.png`.)

## Kurulum — tek satır

```bash
git clone https://github.com/onkanat/hermes-offpeak-bekci && hermes-offpeak-bekci/tools/kur.sh && hermes plugins enable offpeak-bekci
```

`tools/kur.sh` repoyu `$HERMES_HOME/plugins/offpeak-bekci` altına kopyalar (idempotent, uzak
indirme yok), yükleme yüzeyinin sha256'sını basar ve `hermes plugins validate` ile doğrular.

Masaüstü yarısı (rozet) ayrı kurulur — tek dosya:

```bash
mkdir -p ~/.hermes/desktop-plugins/offpeak-bekci
cp desktop/plugin.js ~/.hermes/desktop-plugins/offpeak-bekci/plugin.js
# sonra: Settings ▸ Plugins'ten açın · ⌘K → "Reload desktop plugins"
```

Rozet, durumu `/offpeak-durum json` ile okur; bu yüzden sunucu ve masaüstü yarısını **birlikte**
güncelleyin (aynı sürüm).
Başka bir profil için: `HERMES_HOME=~/.hermes/profiles/<profil> tools/kur.sh`. Bir değeri
değiştirmek için **kod düzenlemek gerekmez**: ayar `config.yaml` → `offpeak-bekci:` bloğuna yazılır.

Katalog girdisi (`plugin-catalog/offpeak-bekci.yaml`): PR
[#139797](https://github.com/NousResearch/hermes-agent/pull/139797) incelemede. Listelenene kadar
yukarıdaki kaynak kurulumu geçerlidir.

## Komutlar

| Komut | Ne yapar |
| --- | --- |
| `/offpeak-durum` | Pencere, geri sayım, kayan pencere hızı, kota ve kuyruk sayacı. **Varsayılan: okunur rapor**; `/offpeak-durum json` makine çıktısı (masaüstü rozeti bunu okur). |
| `/offpeak-onayla <id,id>` | Kuyruk defterindeki kalemleri `onaylı` yapar (onaylayan **tek** yer kullanıcıdır). |
| `/offpeak-kur` | Kurulacak off-peak cron işini **tam** gösterir (iş adı, zamanlama, promptun tamamı, monitör, workdir, araç kümeleri, teslim) + `plan_hash`. **Hiçbir şey kurmaz.** |
| `/offpeak-kur onayla <plan_hash> [duraklat]` | Yalnız `plan_hash` tutuyorsa devam eder; kurulum **isteğini** oturuma bırakır, işi ajanın kendi `cronjob_manage` aracı kurar (host'a bağlı — bkz. *Hangi host'ta otomatik bırakılır?*). |
| `/offpeak-kaldir` | Bu profildeki offpeak işlerini listeler (id · zamanlama · durum · sonraki koşu). |
| `/offpeak-kaldir onayla <job_id>` | Yalnız listedeki bir id ile kaldırma **isteğini** oturuma bırakır (host'a bağlı — bkz. *Hangi host'ta otomatik bırakılır?*). |

Neden "istek"? Eklenti API'sinde cron işi **yaratma** yüzeyi yoktur (`register_command`/hook/
middleware vardır, iş kurucu yoktur). Kurulum bu yüzden kullanıcı onaylı bir mesajla oturuma
bırakılır; kararı ve kaydı ajanın cron aracı yapar. **Eklenti `jobs.json`'a hiçbir koşulda
yazmaz — yalnız okur.**

### Hangi host'ta otomatik bırakılır? (ölçülmüş sınır)

`ctx.inject_message(…)` çağrısını çekirdek host'a göre yönlendirir
(`hermes_cli/plugins_injection.py:18-32`):

| Host | Ne olur |
| --- | --- |
| **Klasik CLI** (terminal REPL) | İstek CLI kuyruğuna girer, dönüş `True`; komut bitince ajan kurar. |
| **Ink TUI (`hermes --tui`) / masaüstü-panel** | Çekirdek **kalıcı `session_key`** ister. O anahtar komut handler'ına verilmez → dönüş `False`. |
| **Gateway oturumu** | İstek o oturuma kuyruklanır — **ama** çekirdek önce kapıyı sorar: `plugins.entries.offpeak-bekci.allow_gateway_injection: true` (varsayılan **kapalı**). Kapalıysa uyarı basılır ve dönüş `False` (`hermes_cli/plugins.py:622-630`). |

Masaüstü/Ink host'unda komut "bu kanalda oturuma bırakılamadı" dalına düşer ve kurulacak
parametreleri **tek satır JSON** olarak basar: iş yine ajanın cron aracıyla kurulur.

Prova (işi kurup hemen kaldırmadan denemek):

```text
/offpeak-kur onayla <plan_hash> duraklat     # iş paused:true kurulur, zamanlanmaz
hermes cron list                             # iş görünür
/offpeak-kaldir onayla <job_id>              # geri alma
```

## Disclosure — ne okur, nereye yazar, ne tutar

**Okur:** yalnız `kuyruk_dosyasi` ayarının gösterdiği tek yerel dosya (varsayılan
`~/.hermes/offpeak-bekci/kuyruk.md`). Kurulum komutları ayrıca cron deposunu
(`<profil>/cron/jobs.json`) **salt okur**; depo yolu **genel yüzeyden** türetilir
(`hermes_constants.get_hermes_home()`), çekirdeğin özel `cron.jobs` modülü **import edilmez**.

**Yazar:** (1) `olcum_dosyasi` günlüğü (JSONL, yerel); (2) kullanıcı `/offpeak-onayla` verdiğinde
**yalnız** `kuyruk_dosyasi` (atomik yazım). Başka hiçbir yere yazmaz; `jobs.json`, `config.yaml` ve
site dosyaları kapsam **dışıdır**.

**Yapmaz:** ağ çağrısı yok, telemetri yok, sır/parola/token okumaz-yazmaz, kabuk/süreç çalıştırmaz,
uzaktan kod indirmez, kendi kendini güncellemez, başka profil/makineye dokunmaz. Masaüstü yarısı
yalnız eklenti SDK yüzeyini kullanır: prototip yamalama, `eval`, DOM sorgulama yok.

## Ayarlar

| Ayar | Varsayılan | Anlamı |
| --- | --- | --- |
| `dil` | `en` | Komut açıklamaları, komut çıktıları ve bildirimlerin dili: `en` veya `tr`. |
| `kuru_kosu` | `true` | `true` iken ölçer/kaydeder, **bekleme uygulamaz**. |
| `kuyruk_dosyasi` | `~/.hermes/offpeak-bekci/kuyruk.md` | Kuyruk defterinin yolu (tek okuma kaynağı). |
| `schedule` | `5 18 * * 1-5` | Off-peak penceresinin açılışı (cron, UTC). |
| `on_bildirim_dk` | `30` | Uyarının pencere öncesi başlangıcı (dk). |
| `hedef_hiz_dk` | `6` | Peak'te dakikada en fazla kaç çağrı. |
| `erteleme_tavani_sn` | `30.0` | Tek istek için en fazla bekleme (gecikme tavanı). |
| `pencere_sn` | `60.0` | Kayan hız penceresinin uzunluğu (sn). |
| `kota_tavani` | `120` | Kota penceresinde en fazla çağrı; aşılırsa uyarı kaydı. |
| `kota_penceresi_sn` | `3600.0` | Kota sayacının penceresi (sn). |
| `kota_token_gun` | `0` | Günlük taze token tavanı; `0` = tavan yok. |
| `cache_read_tavani_gun` | `0` | Günlük cache-read token tavanı; `0` = tavan yok. |
| `off_peak_only_isler` | `[]` | Yalnız off-peak'te koşması gereken iş adları (beyan). |
| `olcum_dosyasi` | `~/.hermes/offpeak-bekci/olcum.jsonl` | Ölçüm/uyarı günlüğü (JSONL, yerel). |

## Geliştirme

```bash
python3 -m unittest discover -s tests -t .   # python kapıları
node --test tests/desktop/plugin.test.mjs    # masaüstü kapıları
node tools/build-desktop.mjs --check         # gömülü plugin.js beyat mı (EXIT=0)
hermes plugins validate . --install-deps     # manifest doğrulaması
```

Sınır: gerçek kuyruk defterine ölçüm amaçlı **yazılmaz**; kurulum komutları kullanıcı onayı
olmadan iş kurmaz ve `kuru_kosu` ayarını değiştirmez.
