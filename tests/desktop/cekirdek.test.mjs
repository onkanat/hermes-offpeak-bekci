/**
 * Masaüstü çekirdeği sınır/karar testleri (saf; tarayıcı yok).
 * Çalıştırma: `node --test tests/desktop/`
 *
 * Pencere kuralları Ollama off-peak tanımından gelir: peak = hafta içi
 * 12:00–18:00 UTC (12:00 dahil, 18:00 hariç); kalan her zaman + hafta sonu = off-peak.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'

import {
  ID,
  kalanSaniye,
  kalemAyristir,
  kuyrukAyristir,
  kuyrukSayilari,
  offpeakAnahtari,
  ozet,
  peakMi,
  pencere,
  sonrakiGecis,
  t30Karari,
  t30Icerisinde,
  geriSayim
} from '../../desktop/bekci-cekirdek.js'

const kok = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const an = iso => Date.parse(iso)

// 2026-10-19 Pazartesi (UTC) haftası: 19 Pzt, 20 Sal, 21 Çar, 22 Per, 23 Cum, 24 Cmt, 25 Paz.
const PZT = '2026-10-19'

test('peak sınırları: 12:00 dahil, 18:00 hariç, hafta sonu hiç peak değil', () => {
  assert.equal(peakMi(an(`${PZT}T11:59:59Z`)), false)
  assert.equal(peakMi(an(`${PZT}T12:00:00Z`)), true)
  assert.equal(peakMi(an(`${PZT}T17:59:59Z`)), true)
  assert.equal(peakMi(an(`${PZT}T18:00:00Z`)), false)
  assert.equal(peakMi(an('2026-10-23T17:59:59Z')), true, 'Cuma 17:59 hâlâ peak')
  assert.equal(peakMi(an('2026-10-23T18:00:00Z')), false, 'Cuma 18:00 → hafta sonu bloğu')
  assert.equal(peakMi(an('2026-10-24T12:00:00Z')), false, 'Cumartesi 12:00 off-peak')
  assert.equal(peakMi(an('2026-10-25T12:00:00Z')), false, 'Pazar 12:00 off-peak')
  assert.equal(pencere(an(`${PZT}T12:00:00Z`)), 'peak')
  assert.equal(pencere(an(`${PZT}T18:00:00Z`)), 'off-peak')
})

test('sonrakiGeçiş her zaman ileri gider ve doğru pencereyi gösterir', () => {
  assert.equal(sonrakiGecis(an(`${PZT}T17:30:00Z`)).an, an(`${PZT}T18:00:00Z`))
  assert.equal(sonrakiGecis(an(`${PZT}T18:00:00Z`)).an, an('2026-10-20T12:00:00Z'), 'Salı 12:00')
  assert.equal(sonrakiGecis(an('2026-10-23T18:30:00Z')).an, an('2026-10-26T12:00:00Z'), 'Cuma akşamı → Pazartesi')
  assert.equal(sonrakiGecis(an('2026-10-24T00:00:00Z')).an, an('2026-10-26T12:00:00Z'), 'Cumartesi → Pazartesi')
  assert.equal(sonrakiGecis(an(`${PZT}T11:00:00Z`)).an, an(`${PZT}T12:00:00Z`))
})

test('kalan saniye ve geri sayım (ceil dakika)', () => {
  assert.equal(kalanSaniye(an(`${PZT}T17:30:00Z`)), 1800)
  assert.equal(geriSayim(an(`${PZT}T17:30:00Z`)), '00:30')
  assert.equal(geriSayim(an(`${PZT}T17:29:59Z`)), '00:31', 'dakika yukarı yuvarlanır')
  assert.equal(geriSayim(an(`${PZT}T16:00:00Z`)), '02:00')
  assert.equal(kalanSaniye(an('2026-10-24T00:00:00Z')), 216000, 'Cumartesi gecesi → 60 saat')
  assert.equal(geriSayim(an('2026-10-24T00:00:00Z')), '60:00')
})

test('off-peak penceresi anahtarı: hafta sonu boyunca tek blok', () => {
  assert.equal(offpeakAnahtari(an(`${PZT}T17:30:00Z`)), an(`${PZT}T18:00:00Z`).valueOf().toString() && new Date(an(`${PZT}T18:00:00Z`)).toISOString())
  assert.equal(offpeakAnahtari(an(`${PZT}T18:00:00Z`)), new Date(an(`${PZT}T18:00:00Z`)).toISOString())
  const cuma = new Date(an('2026-10-23T18:00:00Z')).toISOString()

  assert.equal(offpeakAnahtari(an('2026-10-24T10:00:00Z')), cuma, 'Cumartesi sabahı Cuma bloğu')
  assert.equal(offpeakAnahtari(an('2026-10-25T20:00:00Z')), cuma, 'Pazar akşamı hâlâ aynı blok')
  assert.notEqual(offpeakAnahtari(an('2026-10-26T18:00:00Z')), cuma, 'Pazartesi akşamı yeni blok')
})

test('ozet() Python ile aynı anahtarları taşır', () => {
  const o = ozet(an(`${PZT}T17:45:00Z`))

  for (const k of [
    'simdi_utc', 'pencere', 'peak_mi', 'gelecek_pencere', 'gelecek_gecis_utc',
    'kalan_sn', 'geri_sayim', 't30_dk', 't30_icerisinde', 'offpeak_anahtari'
  ]) {
    assert.ok(k in o, `anahtar eksik: ${k}`)
  }
  assert.equal(o.pencere, 'peak')
  assert.equal(o.gelecek_pencere, 'off-peak')
  assert.equal(o.kalan_sn, 900)
  assert.equal(o.geri_sayim, '00:15')
  assert.equal(o.t30_icerisinde, true)
})

test('T-30 bayrağı: pencere başına BİR kez (enjekte edilen depo)', () => {
  const depo = new Map()
  const sahteDepo = { get: (k, d) => (depo.has(k) ? depo.get(k) : d), set: (k, v) => depo.set(k, v) }

  // eşiğin dışı: kalan 3600 sn > 1800 sn
  const erken = t30Karari(an(`${PZT}T17:00:00Z`), sahteDepo)

  assert.equal(erken.gerekli, false)
  assert.equal(t30Icerisinde(an(`${PZT}T17:00:00Z`)), false)

  // eşiğin içi: kalan 1800 sn → ilk kez gerekli
  const ilk = t30Karari(an(`${PZT}T17:30:00Z`), sahteDepo)

  assert.equal(ilk.gerekli, true)
  assert.equal(ilk.anahtar, `t30:${new Date(an(`${PZT}T18:00:00Z`)).toISOString()}`)

  // bayrağı çağıran yazar (karar fonksiyonu yan etkisizdir)
  sahteDepo.set(ilk.anahtar, true)

  const ikinci = t30Karari(an(`${PZT}T17:31:00Z`), sahteDepo)

  assert.equal(ikinci.gerekli, false)
  assert.equal(ikinci.sebep, 'gonderildi')

  // yeni pencere → yeniden gerekli (Salı 17:30)
  assert.equal(t30Karari(an('2026-10-20T17:30:00Z'), sahteDepo).gerekli, true)

  // off-peak'te hiç tetiklenmez
  assert.equal(t30Karari(an(`${PZT}T19:00:00Z`), sahteDepo).gerekli, false)
  assert.equal(t30Karari(an('2026-10-24T17:30:00Z'), sahteDepo).gerekli, false, 'hafta sonu')
})

test('kuyruk tablosu: kalem satırı sayılır, başlık/ayraç/ölçüm satırı sayılmaz', () => {
  const ornek = [
    '| id | iş | sahip | kanıt ölçütü | durum | pencere |',
    '|----|----|-------|--------------|-------|---------|',
    '| K-001 | **Bağlam sıkıştırma denetimi** | MacAir / default | rapor | onay-bekliyor | Cuma 21:00 |',
    '| K-002 | **Skill envanteri** | MacAir / default | rapor | onaylı | Cuma 21:00 |',
    '| 2026-10-09 | 1.086 | 7.183.437 | 292.606.192 |  |  |',
    '| — | — | — | — | — | — |',
    '- id: K-003 · durum: onay-bekliyor · efor: e-2',
    '- **Salt gövde metni kalem sayılmaz.**',
    '- [ ] K-004 kutulu satır',
    'Düz metin satırı.'
  ].join('\n')
  const kalemler = kuyrukAyristir(ornek)

  assert.deepEqual(kalemler.map(k => k.id), ['K-001', 'K-002', 'K-003', 'K-004'])
  assert.deepEqual(kalemler.map(k => k.durum), ['bekliyor', 'onaylı', 'bekliyor', 'bekliyor'])
  assert.equal(kalemler[2].efor, 'e-2')
  assert.deepEqual(kuyrukSayilari(kalemler), {
    bekleyen: 3, onaylı: 1, beklemede: 3, 'koşuldu': 0, 'atlandı': 0, sahipsiz: 0, toplam: 4
  })
  assert.equal(kalemAyristir('| id | durum |'), null, 'başlık satırı kalem değil')
  assert.equal(kalemAyristir('|---|---|'), null, 'ayraç satırı kalem değil')
})

test('koşum kaydı tablosu kalem sayılmaz + kalın/notlu durum okunur', async () => {
  const { durumHucreYaz } = await import('../../desktop/bekci-cekirdek.js')
  const ornek = [
    '| id | iş | sahip | kanıt ölçütü | durum | pencere |',
    '|----|----|-------|--------------|-------|---------|',
    '| K-001 | **Bağlam** | MacAir / default | rapor | **koşuldu** 16.10.2026 08:26 — çıktı `m/rapor.md` · EXIT=0 | Cuma 21:00 |',
    '| K-002 | **Skill** | MacAir / default | rapor | **onay-bekliyor** (kullanıcı, 16.10.2026 08:05) | Cuma 21:00 |',
    '',
    '### Koşum kaydı',
    '',
    '| id | pencere | başlangıç-bitiş | kanıt satırı | sonuç |',
    '|----|---------|-----------------|--------------|-------|',
    '| K-001 | off-peak (08:23–08:26) | 16.10.2026 08:23 → 08:26 | `m/1.txt` · EXIT=0 | tamam — teşhis: tetik 524.288 |',
    '| K-002 | off-peak (08:24–08:27) | 16.10.2026 08:24 → 08:27 | `m/2.csv` · EXIT=0 | tamam — ayıklama 0 |'
  ].join('\n')
  const kalemler = kuyrukAyristir(ornek)

  // koşum kaydı K-001/K-002 satırları kalem değil → kimlikler yinelenmez
  assert.deepEqual(kalemler.map(k => k.id), ['K-001', 'K-002'])
  assert.deepEqual(kalemler.map(k => k.durum), ['koşuldu', 'bekliyor'])
  // `bekleyen` = "onaysız" (geriye uyumlu tanım, bkz. bekci_core.kuyruk_sayilari);
  // `koşuldu` kalem de onaysız sayılır → 2. Yalnız durumu `bekliyor` olanlar `beklemede`dir.
  assert.deepEqual(kuyrukSayilari(kalemler), {
    bekleyen: 2, onaylı: 0, beklemede: 1, 'koşuldu': 1, 'atlandı': 0, sahipsiz: 0, toplam: 2
  })

  // onaylama yalnız durum sözcüğünü değiştirir: kalın işaret ve ek not korunur
  assert.equal(durumHucreYaz(' **onay-bekliyor** (kullanıcı, 08:05) '), ' **onaylı** (kullanıcı, 08:05) ')
  assert.equal(durumHucreYaz('  '), '  onaylı  ')
})

test('plugin.js tek dosya: yalnız izinli specifier importları + gömülü çekirdek', () => {
  const kaynak = readFileSync(resolve(kok, 'desktop/plugin.js'), 'utf8')
  const importlar = [...kaynak.matchAll(/^\s*import\s+.+?from\s+'([^']+)'/gm)].map(m => m[1])
  const izinli = new Set(['@hermes/plugin-sdk', 'react', 'react/jsx-runtime'])

  assert.ok(importlar.length > 0, 'import bulunamadı')
  for (const i of importlar) {
    assert.ok(izinli.has(i), `yasak specifier (host çözmez): ${i}`)
  }
  assert.ok(!kaynak.includes('/* __CEKIRDEK__ */'), 'işaret gömülmemiş')
  assert.ok(kaynak.includes('export function ozet('), 'çekirdek gömülü değil')
  assert.ok(kaynak.includes(`id: ID`), 'varsayılan eklenti dışa aktarımı yok')
  assert.equal(ID, 'offpeak-bekci', 'klasör adı = id')
})
