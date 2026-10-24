# Off-peak sağlık durumu

> Ölçüm: **24.10.2026 09:05 (+03) / 06:05 UTC** — pencere **AÇIK** (Cmt; sonraki peak Pzt 15:00).
> Bu sayfa elle güncellenir; ölçüm komutları §5'te. Tam bakım kanıtı: `~/MacAir/urunler/offpeak-bekci/kanit/bakim-20261024.md`.

## 1. Zamanlanmış işler

| İş | ID | Aralık | Durum | Son durum |
|---|---|---|---|---|
| `offpeak-kuyruk-kosusu (bekci kapili)` | `6068be95` | 5 dk | **kapalı** (K-043 kararı bekleniyor — bilinçli) | ok |
| `offpeak-kuyruk-kosusu (agy · 0 token)` | `82d98e06` | 30 dk | **kapalı** | delivery_queued |
| `cadbridge-offpeak-dalga` | `697ca1d4` | 10 dk | etkin · `deliver: local` | 62/62 completed (23.10 22:10 düzeltmesinden sonra) |
| `offpeak-urun-nabiz` | `e000937c` | Pzt 09:00 | etkin | ok |
| `offpeak-issue-taslak` | `60df8742` | 15 dk | etkin | ok |

> **Tüketici 0 + onaylı 1 (K-043).** `/offpeak-durum` bunu 0.1.8'den itibaren söylüyor ve **24.10 09:2x'te
> canlı doğrulandı**: `- **queue consumers**: 0/2 enabled — 1 approved item(s) CANNOT run` +
> `… 1 approved but 0 queue consumers enabled — WON'T RUN`. Kurulum pinli yapıldı
> (`revision=e566f91…`); `tools/kur.sh` tek başına provenance'ı güncellemez.

## 2. Açık arızalar

| # | Arıza | Durum (24.10) |
|---|---|---|
| **#1** | Başarısız cron koşumunda bildirim yok | **KAPANDI 24.10**: kök neden `deliver: local` + boş `failure_deliver` (146 `failed`, `alerted_at` NULL). Düzeltme: `697ca1d4` + `147cdf1d` → `failure_deliver: bot-chat`. Sahte işle doğrulandı: 3. ardışık düşüşte `bot-chat` kuyruğa girdi |
| **#2** | Cron, bash betiğini Python gibi koşuyordu | **KAPANDI 24.10** (teşhis düzeltmesiyle): çekirdek `.sh` hedefini zaten bash ile koşuyor (`cron/scheduler_script.py:_script_argv`); `runpy` **bizim sarmalayıcımızdaydı** (`cadbridge_gece.py`). Sarmalayıcı `subprocess.run(["bash", …])`; 23.10 sonrası 62/62 completed |
| **#3** | Tüketici kapalıyken onaylı kalem sessizce bekliyor | **KAPANDI 24.10** (plugin tarafı): `/offpeak-durum` tüketici sayacı + "WON'T RUN" uyarısı (0.1.8). `disabled_reason` alanı çekirdekte yok — upstream işi olarak not edildi |

## 3. Dersler

1. **Sessiz düşüş en pahalı arıza** — 146 başarısız koşum, tek satır bildirim yok. Kök neden kod değil **kanal** (`deliver: local`).
2. **Canlı yama repoda yoksa sürüm onu siler** — 23.10'da kapıya uygulanan başlık biçimi düzeltmesi yalnız kurulu kopyalardaydı; 24.10'da depoya alındı + testlendi.
3. **Derlenmiş yapı kaynaktan kopabilir** — `desktop/plugin.js` yayında bayattı; `build-desktop --check` bu kapıyı atlamayı affetmiyor.
4. **"Kuyruğa aldım" ≠ "koşuyor"** — tüketici sayısı ölçülmeden iddia kurulmaz; artık `/offpeak-durum` sayıyor.
5. **Kod değişikliği ≠ yüklü kod:** `plugins/.install-metadata.json` `revision` alanı eski pinde kalırsa
   (`pinned@004e68…`) restart bile eski kodu servis eder; doğru yol `hermes plugins install <repo> --ref <tam-40-hex> --force --enable`.
6. **`enabled=false` gerekçesiz bırakılmamalı** — `disabled_reason` yoksa "neden koşmuyor" cevapsız (çekirdek alanı; plugin kendi notunu yazamaz).

## 4. Pencere

Hafta içi **12:00–18:00 UTC dışı** + hafta sonu tamamı. Yerel (+03): hafta içi 15:00–21:00 PEAK.
Ölçüm `date -u` ile yapılır, yerel saatten hesaplanmaz.

## 5. Ölçüm komutları

```bash
python3 ~/.hermes/scripts/offpeak_bekci.py --durum   # canlı kapı: ONAYLI / KOSULMAMIŞ
hermes -z "/offpeak-durum"                            # tüketici + pencere raporu
hermes cron list
sqlite3 ~/.hermes/cron/executions.db \
  "select substr(job_id,1,8), status, count(*) from executions
   where started_at >= date('now','-2 day') group by 1,2;"
sqlite3 ~/.hermes/cron/executions.db \
  "select job_id, state, alerted_at, closed_at from cron_incidents order by rowid desc limit 5;"
```

`~/.hermes/cron/jobs.json` içinden etkin bayraklar:

```python
import json, pathlib
j = json.loads(pathlib.Path.home().joinpath(".hermes/cron/jobs.json").read_text())
jobs = j if isinstance(j, list) else j.get("jobs", [])
print([(k["id"][:8], k.get("enabled"), k.get("deliver")) for k in jobs])
```
