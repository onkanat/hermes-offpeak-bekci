# Kuyruk kalemi örneği (test verisi) — gerçek dosyanın biçimi:
# Kuyruk defteri örneği — kullanıcının gerçek defterinden alınmış biçim (yol/sabit değer yok).

| id | iş | sahip | kanıt ölçütü | durum | pencere |
|----|----|-------|--------------|-------|---------|
| K-001 | **Bağlam sıkıştırma denetimi** | MacAir / default | cache_read raporu | onay-bekliyor | Cuma 21:00 → Pzt 15:00 |
| K-002 | **Skill envanteri** | MacAir / default | envanter raporu | onaylı | Cuma 21:00 → Pzt 15:00 |
| K-003 | `KULLANICI-TARTISMA-LISTESI` maddeleri | MacAir / default | kapanan madde sayısı | **koşuldu** 16.10.2026 08:26 — çıktı `maliyet/rapor.md` · EXIT=0 | Cuma 21:00 → Pzt 15:00 |
| K-004 | **Kalın + ek notlu durum** | MacAir / default | kanıt satırı | **onay-bekliyor** (kullanıcı, 16.10.2026 08:05) | Cuma 21:00 → Pzt 15:00 |

| Gün | API çağrısı | taze token | cache_read |
|-----|-------------|------------|------------|
| 2026-10-09 | 1.086 | 7.183.437 | 292.606.192 |
| — | — | — | — |

### Koşum kaydı (kuyruk defteri DEĞİL — durum kolonu yok, kalem sayılmaz)

| id | pencere | başlangıç-bitiş | kanıt satırı | sonuç |
|----|---------|-----------------|--------------|-------|
| K-001 | off-peak (08:23–08:26) | 16.10.2026 08:23 → 08:26 | `maliyet/sorgu.txt` · EXIT=0 | tamam — teşhis: tetik 524.288 |
| K-002 | off-peak (08:24–08:27) | 16.10.2026 08:24 → 08:27 | `skill.csv` · EXIT=0 | tamam — ayıklama 0 |

- id: K-005 · durum: onay-bekliyor · efor: e-3
- **Salt gövde metni kalem sayılmaz.**
