# Off-peak sağlık durumu

> Ölçüm: **23.10.2026 22:19 (+03) / 19:19 UTC** — pencere **AÇIK** (hafta içi 12–18 UTC dışı).
> Bu sayfa elle güncellenir; ölçüm komutları §5'te.

## 1. Zamanlanmış işler

| İş | ID | Aralık | Durum | Son durum |
|---|---|---|---|---|
| `offpeak-kuyruk-kosusu (bekci kapili)` | `6068be95` | 5 dk | **etkin** *(23.10 resume)* | ok |
| `offpeak-kuyruk-kosusu (agy · 0 token)` | `82d98e06` | 30 dk | **kapalı** | delivery_queued |
| `cadbridge-offpeak-dalga` | `697ca1d4` | 10 dk | etkin | 8+ failed → düzeltildi (#2) |
| `offpeak-urun-nabiz` | `e000937c` | Pzt 09:00 | etkin | — |
| `offpeak-issue-taslak` | `60df8742` | 15 dk | etkin | completed |

## 2. Açık arızalar

| # | Arıza | Durum |
|---|---|---|
| **#1** | Başarısız cron koşumu bildirim üretmiyor (8 kez sessiz düşüş) | açık |
| **#2** | Cron, bash betiğini Python gibi koşuyordu (`runpy` → `SyntaxError`) | **düzeltildi** (bash alt süreç, EXIT=0); kalıcı önlem açık |
| **#3** | Tüketici kapalıyken onaylı kalem sessizce bekliyor | kısmen (`6068be95` resume edildi) |

## 3. Dersler

1. **Sessiz düşüş en pahalı arıza** — sağlık bildirimi şart (#1).
2. **Yorumlayıcı uyuşmazlığı sessizdir** — `.sh` betiği `runpy` ile yüklenince hata *sonra* çıkar (#2).
3. **`enabled=false` gerekçesiz bırakılmamalı** — `disabled_reason` yoksa "neden koşmuyor" cevapsız (#3).
4. **"Kuyruğa aldım" ≠ "koşuyor"** — tüketici sayısı ölçülmeden iddia kurulmaz.

## 4. Pencere

Hafta içi **12:00–18:00 UTC dışı** + hafta sonu tamamı. Yerel (+03): hafta içi 15:00–21:00 PEAK.
Ölçüm `date -u` ile yapılır, yerel saatten hesaplanmaz.

## 5. Ölçüm komutları

```bash
hermes cron list
sqlite3 ~/.hermes/cron/executions.db \
  "select substr(job_id,1,8), status from executions order by rowid desc limit 10;"
```

`~/.hermes/cron/jobs.json` içinden etkin bayrakları:

```python
import json, pathlib
j = json.loads(pathlib.Path.home().joinpath(".hermes/cron/jobs.json").read_text())
jobs = j if isinstance(j, list) else j.get("jobs", [])
print([(k["id"][:8], k.get("enabled")) for k in jobs])
```
