# Kuyruk kalemi örneği (test verisi) — gerçek dosyanın biçimi:
# `~/MacAir/off-peak-kuyruk.md` → "Kuyruk (aktif)" tablosu.

| id | iş | sahip | kanıt ölçütü | durum | pencere |
|----|----|-------|--------------|-------|---------|
| K-001 | **Bağlam sıkıştırma denetimi** | MacAir / default | cache_read raporu | onay-bekliyor | Cuma 21:00 → Pzt 15:00 |
| K-002 | **Skill envanteri** | MacAir / default | envanter raporu | onaylı | Cuma 21:00 → Pzt 15:00 |
| K-003 | `KULLANICI-TARTISMA-LISTESI` maddeleri | MacAir / default | kapanan madde sayısı | onay-bekliyor | Cuma 21:00 → Pzt 15:00 |

| Gün | API çağrısı | taze token | cache_read |
|-----|-------------|------------|------------|
| 2026-10-09 | 1.086 | 7.183.437 | 292.606.192 |
| — | — | — | — |

- id: K-004 · durum: onay-bekliyor · efor: e-3
- **Salt gövde metni kalem sayılmaz.**
