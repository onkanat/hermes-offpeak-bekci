# Off-peak sağlık durumu

> Ölçüm: **24.10.2026 08:40 (+03) / 05:40 UTC** — pencere **AÇIK** (Cmt; sonraki peak Pzt 15:00).
> Bu sayfa elle güncellenir; ölçüm komutları §5'te. Tam bakım kanıtı: `~/MacAir/urunler/offpeak-bekci/kanit/bakim-20261024.md`.

## 1. Zamanlanmış işler

| İş | ID | Aralık | Durum | Son durum |
|---|---|---|---|---|
| `offpeak-kuyruk-kosusu (bekci kapili)` | `6068be95` | 5 dk | **kapalı** (K-043 kararı bekleniyor — bilinçli) | ok |
| `offpeak-kuyruk-kosusu (agy · 0 token)` | `82d98e06` | 30 dk | **kapalı** | delivery_queued |
| `cadbridge-offpeak-dalga` | `697ca1d4` | 10 dk | etkin · `deliver: local` | 62/62 completed (23.10 22:10 düzeltmesinden sonra) |
| `offpeak-urun-nabiz` | `e000937c` | Pzt 09:00 | etkin | ok |
| `offpeak-issue-taslak` | `60df8742` | 15 dk | etkin | ok |

> **Tüketici 0 + onaylı 1 (K-043).** `/offpeak-durum` bunu artık söylüyor:
> `1 approved but 0 queue consumers enabled — WON'T RUN` (0.1.8 ile gelir; kurulu 0.1.7'de yok).

## 2. Açık arızalar

| # | Arıza | Durum (24.10) |
|---|---|---|
| **#1** | Başarısız cron koşumunda bildirim yok | **kök neden ölçüldü**: `697ca1d4` 22.10 21:05 → 23.10 22:10 arası **146 kez failed**, `cron_incidents.alerted_at` **NULL** — işin teslim kanalı `deliver: local` (`cron/scheduler.py:3141` erken dönüş). Düzeltme kanal ayarı; **onay bekliyor** |
| **#2** | Cron, bash betiğini Python gibi koşuyordu | yerel yama `cadbridge_gece.py` (subprocess bash) — 23.10 sonrası 62/62 completed. **Kalıcı çözüm çekirdekte** (`cron/scheduler_script.py:318` hâlâ `runpy.run_path`); upstream taslak hazır, dış yazım onayda |
| **#3** | Tüketici kapalıyken onaylı kalem sessizce bekliyor | **kısmen kapandı**: `/offpeak-durum` tüketici sayacı + uyarı (0.1.8). `disabled_reason` alanı çekirdekte yok — upstream işi |

## 3. Dersler

1. **Sessiz düşüş en pahalı arıza** — 146 başarısız koşum, tek satır bildirim yok. Kök neden kod değil **kanal** (`deliver: local`).
2. **Canlı yama repoda yoksa sürüm onu siler** — 23.10'da kapıya uygulanan başlık biçimi düzeltmesi yalnız kurulu kopyalardaydı; 24.10'da depoya alındı + testlendi.
3. **Derlenmiş yapı kaynaktan kopabilir** — `desktop/plugin.js` yayında bayattı; `build-desktop --check` bu kapıyı atlamayı affetmiyor.
4. **"Kuyruğa aldım" ≠ "koşuyor"** — tüketici sayısı ölçülmeden iddia kurulmaz; artık `/offpeak-durum` sayıyor.
5. **`enabled=false` gerekçesiz bırakılmamalı** — `disabled_reason` yoksa "neden koşmuyor" cevapsız (çekirdek alanı; plugin kendi notunu yazamaz).

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
