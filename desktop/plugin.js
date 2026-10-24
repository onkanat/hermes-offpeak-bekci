/**
 * offpeak-bekci — masaüstü kabuğu (Hermes desktop plugin, tek dosya).
 *
 * KURULUM: `tools/build-desktop.mjs` bu dosyayı `desktop/bekci-cekirdek.js` ile
 * birleştirip `desktop/plugin.js` üretir; kurulum o tek dosyayı
 * `~/.hermes/desktop-plugins/offpeak-bekci/plugin.js` yoluna kopyalar
 * (klasör adı = id). Yükleme: ⌘K → "Reload desktop plugins".
 *
 * Plain ESM, derlenmeden yüklenir — UI jsx() çağrılarıyla (JSX sözdizimi DEĞİL).
 * Host yalnız şu specifier'ları çözer: @hermes/plugin-sdk, react, react/jsx-runtime.
 * Göreli import YASAK olduğu için pencere matematiği tek dosyaya gömülür (üstteki
 * `__CEKIRDEK__` işareti); sınanabilirliği `node --test` + `tests/` sağlar.
 */

import { STATUSBAR_AREAS, TITLEBAR_AREAS, Tip, atom, cn, host, usePluginI18n, useValue } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'

// ── GÖMÜLÜ ÇEKİRDEK (kaynak: desktop/bekci-cekirdek.js — elle düzenlemeyin) ──
/**
 * offpeak-bekci — masaüstü **çekirdeği** (SAF).
 *
 * Bu dosya HİÇBİR ŞEY import etmez: `tools/build-desktop.mjs` onu `desktop/kabuk.js`
 * içindeki `__CEKIRDEK__` işaretine gömerek `desktop/plugin.js` üretir. Böylece
 * masaüstü eklentisi tek dosya kalır (host yalnız `@hermes/plugin-sdk`, `react`,
 * `react/jsx-runtime` specifier'larını çözer; göreli import YASAK) ama pencere
 * matematiği `node --test` ile doğrudan sınanabilir.
 *
 * KAYNAK (off-peak tanımı, Ollama):
 *   "Off-peak pricing apply outside 12:00 and 18:00 UTC on weekdays and all day
 *    on weekends." — https://ollama.com/pricing
 * => peak = hafta içi 12:00–18:00 UTC (12:00 dahil, 18:00 hariç);
 *    kalan her zaman + hafta sonunun tamamı = off-peak.
 *
 * Python tarafındaki `bekci_core.py` aynı kuralları uygular; `tests/test_parite.py`
 * iki uygulamayı aynı anlar için karşılaştırır (tek doğruluk kaynağı: pencere kuralları).
 */

export const ID = 'offpeak-bekci'

/** Hafta içi günler, JS `getUTCDay()` numaralandırması (0=Pazar … 6=Cumartesi). */
export const PEAK_GUNLER = [1, 2, 3, 4, 5]
export const PEAK_BASLANGIC_SAAT = 12
export const PEAK_BITIS_SAAT = 18

export const PENCERE_PEAK = 'peak'
export const PENCERE_OFFPEAK = 'off-peak'

export const ONAYLI = 'onaylı'
export const BEKLIYOR = 'bekliyor'

/** Kuyruk kalemi bildirim eşiği: pencere açılmadan bu kadar dakika önce (eşik E1). */
export const ON_BILDIRIM_DK = 30

/** Eski ad (geriye uyum) — `plugin.yaml`'daki ayar adı `on_bildirim_dk`'dır. */
export const T30_DK = ON_BILDIRIM_DK

/** Rozet başlığında gösterilen kaynak cümlesi. */
export const KAYNAK =
  'Ollama: "Off-peak pricing apply outside 12:00 and 18:00 UTC on weekdays and all day on weekends."'

/**
 * Ortak ayar adları — py `bekci_core.VARSAYILAN_AYARLAR` (= `plugin.yaml` → `config_schema`)
 * ile AYNI küme. Yeni ayar eklerken ikisi birlikte büyür: `tests/test_ayarlar.py` ayrışmayı
 * yakalar (bu liste `plugin.yaml`'dan türetilmez çünkü masaüstü dosyası tek başına yüklenir).
 */
export const ORTAK_AYAR_ANAHTARLARI = [
  'kuru_kosu',
  'kuyruk_dosyasi',
  'schedule',
  'on_bildirim_dk',
  'kota_token_gun',
  'cache_read_tavani_gun',
  'hedef_hiz_dk',
  'erteleme_tavani_sn',
  'off_peak_only_isler',
  'pencere_sn',
  'kota_penceresi_sn',
  'kota_tavani',
  'olcum_dosyasi',
  'dil'
]

/** Yalnız masaüstü yarısına özel ayarlar (çekirdek/backend karşılığı yok). */
export const YEREL_AYAR_ANAHTARLARI = ['tik_ms', 'geri_sayim_esigi_sn']

/**
 * Varsayılanlar — BEYAN KAYNAĞI değil, masaüstü yedeği: gerçek varsayılanlar `plugin.yaml` →
 * `config_schema`'dadır ve backend `/offpeak-durum` yanıtının `ayar` alanıyla gelir. Burada
 * yalnız ağ erişilemezken makul bir rozet çizilecek kadar genel değer durur. Kullanıcıya özel
 * hiçbir yol/değer gömülmez (kuyruk dosyası dahil).
 */
export const VARSAYILAN_AYAR = {
  on_bildirim_dk: ON_BILDIRIM_DK,
  kuru_kosu: true,
  kuyruk_dosyasi: '~/.hermes/offpeak-bekci/kuyruk.md',
  tik_ms: 30_000,
  geri_sayim_esigi_sn: 12 * 60 * 60
}

/**
 * Ortak ayarların TİPLERİ — py `ayarlari_birlestir` ile aynı zorlama, `plugin.yaml` → `type`
 * alanının masaüstü yansıması. `tests/test_ayarlar.py` bu haritayı `plugin.yaml` tipleriyle
 * karşılaştırır: yeni ayar eklerken buranın atlanması sessizce geçmez.
 */
export const AYAR_TIPLERI = {
  kuru_kosu: 'mantik',
  kuyruk_dosyasi: 'metin',
  schedule: 'metin',
  on_bildirim_dk: 'tam',
  kota_token_gun: 'tam',
  cache_read_tavani_gun: 'tam',
  hedef_hiz_dk: 'tam',
  erteleme_tavani_sn: 'ondalik',
  off_peak_only_isler: 'liste',
  pencere_sn: 'ondalik',
  kota_penceresi_sn: 'ondalik',
  kota_tavani: 'tam',
  olcum_dosyasi: 'metin',
  dil: 'metin'
}

/** py `_bool` ile aynı doğru kümesi (kalan her şey yanlış sayılır). */
const DOGRU_METINLERI = new Set(['1', 'true', 'yes', 'evet', 'on', 'açık', 'acik'])

/** Değeri beyan edilen tipe zorlar; çevrilemeyen değer için `null` (varsayılan korunur). */
function ayarCevir(ad, deger) {
  const tip = AYAR_TIPLERI[ad]

  if (tip === 'mantik') {
    return typeof deger === 'boolean' ? deger : DOGRU_METINLERI.has(String(deger).trim().toLowerCase())
  }
  if (tip === 'liste') {
    if (Array.isArray(deger)) {
      return [...deger]
    }
    if (typeof deger === 'string') {
      return deger.split(',').map(p => p.trim()).filter(Boolean)
    }

    return null
  }
  if (tip === 'metin') {
    return String(deger)
  }
  if (tip === undefined) {
    return null // bilinmeyen anahtar (yalnız masaüstüne özel anahtarlar buraya düşer)
  }

  const sayi = sayiCevir(deger)

  if (sayi === null) {
    return null
  }

  return tip === 'tam' ? Math.trunc(sayi) : sayi
}

/** Sayıya çevirir; boş/çevrilemeyen metin için `null` (py `_sayi` gibi: `''` varsayılanı ezmez). */
function sayiCevir(deger) {
  if (typeof deger === 'number') {
    return Number.isFinite(deger) ? deger : null
  }
  const metin = String(deger).trim()

  if (metin === '') {
    return null
  }
  const sayi = Number(metin)

  return Number.isFinite(sayi) ? sayi : null
}

/** Yalnız masaüstüne özel sayısal ayarı çevirir (çekirdek karşılığı yok). */
function yerelCevir(deger) {
  return sayiCevir(deger)
}

/** Tek kaynağı temizler: bilinmeyen anahtar atılır, eski ad kanonik adına çevrilir, tip zorlanır. */
function ayarTemizle(kaynak) {
  const temiz = {}
  const kanonikGeldi = new Set()

  for (const [anahtar, deger] of Object.entries(kaynak)) {
    if (deger === null || deger === undefined) {
      continue
    }
    const ad = anahtar === 't30_dk' ? 'on_bildirim_dk' : anahtar
    const yerel = YEREL_AYAR_ANAHTARLARI.includes(ad)

    if (!yerel && !ORTAK_AYAR_ANAHTARLARI.includes(ad)) {
      continue
    }
    if (kanonikGeldi.has(ad) && anahtar !== ad) {
      continue // aynı kaynakta kanonik ad takma addan üstündür
    }
    const cevrilen = yerel ? yerelCevir(deger) : ayarCevir(ad, deger)

    if (cevrilen === null) {
      continue // çevrilemeyen değer varsayılanı ezmez
    }
    temiz[ad] = cevrilen
    kanonikGeldi.add(ad)
  }

  return temiz
}

/**
 * Ayar kaynaklarını soldan sağa ezer (son kazanan): varsayılan → `ctx.config` → backend'in
 * beyan ettiği etkin ayarlar. py `ayarlari_birlestir` ile aynı kurallar (bilinmeyeni at,
 * `t30_dk` → `on_bildirim_dk`, boş değeri yok say).
 */
export function ayarlariBirlestir(...kaynaklar) {
  const sonuc = { ...VARSAYILAN_AYAR }

  for (const kaynak of kaynaklar) {
    if (!kaynak || typeof kaynak !== 'object' || Array.isArray(kaynak)) {
      continue
    }
    Object.assign(sonuc, ayarTemizle(kaynak))
  }

  return sonuc
}

const GUN_MS = 86_400_000

/** Aynı UTC gününün verilen saatini döner (dakika/saniye sıfır). */
export function saatBasi(ms, saat) {
  const d = new Date(ms)

  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), saat, 0, 0, 0)
}

/** Hafta içi 12:00–18:00 UTC mi? (12:00 dahil, 18:00 hariç) */
export function peakMi(ms) {
  const d = new Date(ms)

  return PEAK_GUNLER.includes(d.getUTCDay()) && d.getUTCHours() >= PEAK_BASLANGIC_SAAT && d.getUTCHours() < PEAK_BITIS_SAAT
}

/** `'peak'` veya `'off-peak'`. */
export function pencere(ms) {
  return peakMi(ms) ? PENCERE_PEAK : PENCERE_OFFPEAK
}

/** (gelecek pencerenin adı, geçiş anı ms) — her zaman şimdiden sonradır. */
export function sonrakiGecis(ms) {
  if (peakMi(ms)) {
    return { ad: PENCERE_OFFPEAK, an: saatBasi(ms, PEAK_BITIS_SAAT) }
  }
  let aday = saatBasi(ms, PEAK_BASLANGIC_SAAT)

  if (aday <= ms) {
    aday += GUN_MS
  }
  while (!PEAK_GUNLER.includes(new Date(aday).getUTCDay())) {
    aday += GUN_MS
  }

  return { ad: PENCERE_PEAK, an: aday }
}

/** Gelecek pencere değişimine kalan saniye (tam sayı, aşağı yuvarlı). */
export function kalanSaniye(ms) {
  return Math.floor((sonrakiGecis(ms).an - ms) / 1000)
}

/** `'HH:MM'` — dakika yukarı yuvarlanır (00:00 yalnız gerçekten 0'da görünür). */
export function geriSayim(ms) {
  const kalan = Math.max(0, kalanSaniye(ms))
  const toplamDk = Math.ceil(kalan / 60)
  const saat = Math.floor(toplamDk / 60)
  const dk = toplamDk % 60

  return `${String(saat).padStart(2, '0')}:${String(dk).padStart(2, '0')}`
}

/** Ayar sözlüğünden hatırlatma eşiğini (dk) çıkarır; yoksa genel varsayılan. */
function ayarDk(ayar) {
  const ham = ayar?.on_bildirim_dk ?? ayar?.t30_dk

  return Number.isFinite(ham) ? ham : ON_BILDIRIM_DK
}

/** Off-peak'e `dk` dakika veya daha az kaldıysa true (yalnız peak'te). */
export function t30Icerisinde(ms, dk = ON_BILDIRIM_DK) {
  if (!peakMi(ms)) {
    return false
  }

  return kalanSaniye(ms) <= Math.max(0, Math.trunc(dk)) * 60
}

/** İçinde olunan/yaklaşılan off-peak bloğunun kimliği (ISO-8601 UTC). */
export function offpeakAnahtari(ms) {
  let bas = saatBasi(ms, PEAK_BITIS_SAAT)

  if (!peakMi(ms) && bas > ms) {
    bas -= GUN_MS
  }
  while (!PEAK_GUNLER.includes(new Date(bas).getUTCDay())) {
    bas -= GUN_MS
  }

  return new Date(bas).toISOString()
}

/** Rozet/komut için tek çağrıda pencere özeti (saf). Python `ozet()` ile aynı anahtarlar. */
export function ozet(ms, ayar = VARSAYILAN_AYAR) {
  const t30Dk = ayarDk(ayar)
  const gecis = sonrakiGecis(ms)

  return {
    simdi_utc: new Date(ms).toISOString(),
    pencere: pencere(ms),
    peak_mi: peakMi(ms),
    gelecek_pencere: gecis.ad,
    gelecek_gecis_utc: new Date(gecis.an).toISOString(),
    kalan_sn: kalanSaniye(ms),
    geri_sayim: geriSayim(ms),
    t30_dk: Math.trunc(t30Dk),
    t30_icerisinde: t30Icerisinde(ms, t30Dk),
    offpeak_anahtari: offpeakAnahtari(ms)
  }
}

/**
 * "Pencere başına 1 kez" bildirim kararı.
 *
 * `depo` = `{ get(anahtar, varsayilan), set(anahtar, deger) }` (host: `ctx.storage`).
 * Yan etki YOK: bayrağı çağıran taraf `depo.set(anahtar, true)` ile yazar; böylece
 * karar enjekte edilen `ms` + depo ile testte birebir sınanabilir.
 */
export function t30Karari(ms, depo, ayar = VARSAYILAN_AYAR) {
  const anahtar = `t30:${offpeakAnahtari(ms)}`

  if (!t30Icerisinde(ms, ayarDk(ayar))) {
    return { gerekli: false, anahtar, sebep: 'pencere-yok' }
  }
  if (depo && depo.get(anahtar, false) === true) {
    return { gerekli: false, anahtar, sebep: 'gonderildi' }
  }

  return { gerekli: true, anahtar, sebep: 'ilk' }
}

// ── Kuyruk ayrıştırma (Python `kuyruk_ayristir` ile aynı kurallar) ────────────

const DURUM_ESANLAMLILARI = {
  onaylı: ONAYLI,
  onaylandi: ONAYLI,
  onaylandı: ONAYLI,
  approved: ONAYLI,
  ok: ONAYLI,
  done: ONAYLI,
  tamam: ONAYLI,
  onay: ONAYLI,
  x: ONAYLI,
  bekliyor: BEKLIYOR,
  'onay-bekliyor': BEKLIYOR,
  'onay bekliyor': BEKLIYOR,
  'onay-beklemede': BEKLIYOR,
  beklemede: BEKLIYOR,
  pending: BEKLIYOR,
  open: BEKLIYOR,
  taslak: BEKLIYOR,
  sırada: BEKLIYOR,
  sirada: BEKLIYOR,
  koşuldu: 'koşuldu',
  kosuldu: 'koşuldu',
  'koşuldu.': 'koşuldu',
  'çalıştırıldı': 'koşuldu',
  calistirildi: 'koşuldu',
  ran: 'koşuldu',
  'atlandı': 'atlandı',
  atlandi: 'atlandı',
  skipped: 'atlandı',
  iptal: 'atlandı',
  reddedildi: 'atlandı',
  rejected: 'atlandı',
  sahipsiz: 'sahipsiz',
  'atanmamış': 'sahipsiz',
  atanmamis: 'sahipsiz',
  ownerless: 'sahipsiz',
  unassigned: 'sahipsiz'
}

const TABLO_BASLIKLARI = new Set([
  'id', 'iş', 'is', 'kalem', 'sahip', 'owner', 'kanıt', 'kanit', 'kanıt/dosya',
  'durum', 'status', 'pencere', 'efor', 'effort', 'not', 'notlar', 'başlık', 'baslik'
])

/** Tablo başlığında durum kolonunu bildiren hücre adları (kuyruk defteri ölçütü). */
const DURUM_BASLIKLARI = new Set(['durum', 'status'])
/** Tablo başlığında kimlik kolonunu bildiren hücre adları. */
const ID_BASLIKLARI = new Set(['id', 'kimlik', 'kalem', 'iş', 'is'])
/** Baş sözcük eşleşmesinde kullanılmayan kısa eşanlamlılar (gürültüye açık: "x", "ok", "tamam"). */
const DURUM_ONEK_DISLA = new Set(['x', 'ok', 'tamam', 'done', 'onay'])

const TABLO_ID = /^`?[A-Za-z]{1,6}-?\d+`?$/
const TABLO_EFOR = /^`?e-\d+`?$/i
const TABLO_AYRAC_HUCRE = /^:?-{2,}:?$/
const ID_ALANI = /(?:^|[\s|·;,])(?:id|kimlik)\s*[:=]\s*([^\s|·;,]+)/i
const DURUM_ALANI = /(?:^|[\s|·;,])(?:durum|status)\s*[:=]\s*([^\s|·;,]+)/i
const SATIR_KALEMI = /^\s*(?:[-*+]|\d+[.)])\s+(.*)$/
const KUTU_ISARETI = /^\[( |x|X)\]\s*(.*)$/

function temizle(hucre) {
  return String(hucre ?? '').trim().replace(/^[`*_]+|[`*_]+$/g, '')
}

function durumNormallestir(ham, kutu) {
  if (ham) {
    const d = temizle(ham).toLowerCase()

    return DURUM_ESANLAMLILARI[d] ?? d
  }
  if (kutu !== null && kutu !== undefined && String(kutu).toLowerCase() === 'x') {
    return ONAYLI
  }

  return BEKLIYOR
}

/** Hücrenin BAŞ sözcüğünü durum sözlüğünde arar (ör. `**koşuldu** 16.10.2026 …`). */
function durumOnek(hucre) {
  const t = temizle(hucre).trim()

  if (!t) {
    return null
  }
  const ilk = t.split(/[\s`*_]+/)[0].replace(/[`*_.:,;]+$/g, '').toLowerCase()

  if (!ilk || DURUM_ONEK_DISLA.has(ilk)) {
    return null
  }

  return DURUM_ESANLAMLILARI[ilk] ?? null
}

/** Durum hücresi: önce birebir sözcük, sonra baş sözcük. Boşsa null. */
function durumHucre(hucre) {
  const t = String(hucre ?? '').trim()

  if (!t) {
    return null
  }
  const duz = temizle(t).trim().toLowerCase()

  if (DURUM_ESANLAMLILARI[duz] !== undefined) {
    return DURUM_ESANLAMLILARI[duz]
  }

  return durumOnek(t)
}

/** Durum hücresinde YALNIZ durum sözcüğünü değiştirir: kalın işaret ve ek not korunur. */
export function durumHucreYaz(ham) {
  const h = String(ham ?? '')
  const m = /^(\s*[`*_]*)([^\s`*_]+)/.exec(h)

  if (!m) {
    const bas = /^\s*/.exec(h)[0]
    const son = /\s*$/.exec(h)[0]

    return (bas || ' ') + ONAYLI + (son || ' ')
  }

  return h.slice(0, m[1].length) + ONAYLI + h.slice(m[1].length + m[2].length)
}

/** `| a | b |` satırını hücrelere çözer (ayraç satırı DA döner); tablo değilse null. */
function tabloHucreleriHam(satir) {
  const m = /^\s*\|(.+)\|\s*$/.exec(satir ?? '')

  if (!m) {
    return null
  }
  const ic = m[1]
  const hucreler = []
  const re = /[^|]+/g
  let hm = re.exec(ic)

  while (hm) {
    hucreler.push({ ham: hm[0], bas: hm.index, son: hm.index + hm[0].length })
    hm = re.exec(ic)
  }

  return hucreler.length ? { ic, hucreler } : null
}

function ayracSatiriMi(hucreler) {
  return (
    Array.isArray(hucreler) &&
    hucreler.length > 0 &&
    hucreler.every(h => TABLO_AYRAC_HUCRE.test(String(h.ham).trim()) || !String(h.ham).trim())
  )
}

/** `| a | b |` satırını hücrelere çözer; tablo değilse/ayraçsa null. */
function tabloHucreleri(satir) {
  const t = tabloHucreleriHam(satir)

  if (!t || ayracSatiriMi(t.hucreler)) {
    return null
  }

  return t
}

/**
 * Tablo satırlarını (1 tabanlı satır no) tablonun başlık bilgisine eşler.
 * Başlığında `durum`/`status` kolonu olmayan tablo kuyruk defteri değildir (koşum kaydı,
 * ölçüm tablosu): satırları kalem sayılmaz. Başlıksız tablolar için değer null (eski davranış).
 */
export function tabloBaslikHaritasi(satirlar) {
  const harita = new Map()
  const liste = Array.isArray(satirlar) ? satirlar.map(s => String(s ?? '').replace(/\r$/, '')) : []
  let i = 0

  while (i < liste.length) {
    if (!tabloHucreleriHam(liste[i])) {
      i += 1
      continue
    }
    const blok = []

    while (i < liste.length) {
      const h = tabloHucreleriHam(liste[i])

      if (!h) {
        break
      }
      blok.push({ no: i + 1, hucreler: h.hucreler })
      i += 1
    }
    let veri = blok
    let baslikBilgisi = null

    if (blok.length >= 2 && ayracSatiriMi(blok[1].hucreler)) {
      const baslik = blok[0].hucreler.map(h => temizle(h.ham).toLowerCase())
      const durumIdx = baslik.findIndex(t => DURUM_BASLIKLARI.has(t))
      const idIdx = baslik.findIndex(t => ID_BASLIKLARI.has(t))

      baslikBilgisi = {
        durum_idx: durumIdx < 0 ? null : durumIdx,
        id_idx: idIdx < 0 ? null : idIdx
      }
      veri = blok.slice(2)
    }
    for (const { no, hucreler } of veri) {
      if (ayracSatiriMi(hucreler)) {
        continue
      }
      harita.set(no, baslikBilgisi)
    }
  }

  return harita
}

/** Tek satırı kaleme çevirir; kalem değilse null. */
export function kalemAyristir(satir, no = 0, baslik = null) {
  const tablo = tabloHucreleri(satir)

  if (tablo) {
    const { hucreler } = tablo
    const temiz = hucreler.map(h => temizle(h.ham))
    const dolu = temiz.filter(Boolean)

    if (!dolu.length || dolu.every(t => TABLO_BASLIKLARI.has(t.toLowerCase()))) {
      return null
    }
    if (baslik) {
      // Başlığında durum kolonu YOKSA bu tablo kuyruk defteri değildir (koşum kaydı vb.).
      if (baslik.durum_idx === null || baslik.durum_idx === undefined) {
        return null
      }
      const dIdx = baslik.durum_idx
      let kidHam =
        baslik.id_idx !== null && baslik.id_idx !== undefined ? temiz[baslik.id_idx] : ''

      if (!kidHam || !TABLO_ID.test(kidHam)) {
        kidHam = temiz.find(t => TABLO_ID.test(t))
      }
      if (!kidHam || dIdx >= temiz.length) {
        return null
      }

      return {
        id: kidHam.replace(/`/g, ''),
        durum: durumHucre(temiz[dIdx]) ?? BEKLIYOR,
        efor: temiz.find(t => TABLO_EFOR.test(t)) ?? '',
        satir_no: no,
        metin: String(satir).trim()
      }
    }
    const kidHam = temiz.find(t => TABLO_ID.test(t))

    if (!kidHam || hucreler.length < 4) {
      return null
    }
    const durumHam = temiz.find(t => DURUM_ESANLAMLILARI[t.toLowerCase()] !== undefined)
    const durum =
      durumHam !== undefined
        ? DURUM_ESANLAMLILARI[durumHam.toLowerCase()]
        : (temiz.map(t => durumOnek(t)).find(Boolean) ?? BEKLIYOR)
    const eforHam = temiz.find(t => TABLO_EFOR.test(t))

    return {
      id: kidHam.replace(/`/g, ''),
      durum,
      efor: eforHam ?? '',
      satir_no: no,
      metin: String(satir).trim()
    }
  }
  const m = SATIR_KALEMI.exec(satir ?? '')

  if (!m) {
    return null
  }
  let govde = m[1].trim()
  let kutu = null
  const km = KUTU_ISARETI.exec(govde)

  if (km) {
    kutu = km[1]
    govde = km[2].trim()
  }
  const im = ID_ALANI.exec(govde)
  let kid = ''

  if (im) {
    kid = im[1].trim()
  } else if (kutu !== null) {
    kid = (govde.split(/[\s|·;,]+/)[0] ?? '').replace(/^[`*_]+|[`*_]+$/g, '')
  } else {
    return null
  }
  if (!kid) {
    return null
  }
  const dm = DURUM_ALANI.exec(govde)
  const em = /(?:^|[\s|·;,])(?:efor|effort)\s*[:=]\s*([^\s|·;,]+)/i.exec(govde)

  return {
    id: kid,
    durum: durumNormallestir(dm ? dm[1] : null, kutu),
    efor: em ? em[1].trim() : '',
    satir_no: no,
    metin: govde
  }
}

/** Kuyruk markdown'ını kalem listesine çevirir (tablo + `id:`/kutu madde biçimi). */
export function kuyrukAyristir(metin) {
  const kalemler = []
  const satirlar = String(metin ?? '').split('\n')
  const basliklar = tabloBaslikHaritasi(satirlar)

  for (let i = 0; i < satirlar.length; i += 1) {
    const kalem = kalemAyristir(
      satirlar[i].replace(/\r$/, ''),
      i + 1,
      basliklar.get(i + 1) ?? null
    )

    if (kalem) {
      kalemler.push(kalem)
    }
  }

  return kalemler
}

/**
 * `{onaylı, beklemede, koşuldu, atlandı, sahipsiz, onaysiz, onay_bekleyen, bekleyen, toplam}` (Python ile aynı).
 *
 * Bölüşüm: `onaylı + beklemede + koşuldu + atlandı + sahipsiz === toplam`.
 * `onaysiz` kesişen sayaçtır (onaylı olmayan her kalem, koşuldu dahil) — bölüşüme girmez.
 * `bekleyen` = `onaysiz`ın eski adı (geriye uyumluluk); rozet metni `onay_bekleyen` kullanır.
 */
export function kuyrukSayilari(kalemler) {
  const liste = Array.isArray(kalemler) ? kalemler : []
  const onayli = liste.filter(k => k?.durum === ONAYLI).length
  const beklemede = liste.filter(k => k?.durum === BEKLIYOR).length
  const kosuldu = liste.filter(k => k?.durum === 'koşuldu').length
  const atlandi = liste.filter(k => k?.durum === 'atlandı').length
  const sahipsiz = liste.filter(k => k?.durum === 'sahipsiz').length
  const onaysiz = liste.length - onayli

  return {
    'onaylı': onayli,
    beklemede,
    'koşuldu': kosuldu,
    'atlandı': atlandi,
    sahipsiz,
    onaysiz,
    onay_bekleyen: liste.length - onayli - kosuldu - atlandi,
    bekleyen: onaysiz, // DEPRECATED alias
    toplam: liste.length
  }
}

/**
 * Rozet metni — dil bağımsız iskelet; sözcükleri `kabuk.js` i18n ile dizer.
 * `{pencere, geri_sayim, bekleyen, onaylı}` alanları döner.
 */
export function rozetParcalari(o, sayilar) {
  return {
    pencere: o.pencere,
    geri_sayim: o.geri_sayim,
    // Gerçekten iş bekleyen (onaysiz DEĞİL): onay bekleyen + sahipsiz. Eski eklentide alan yoksa `bekleyen`e düşer.
    bekleyen: sayilar?.onay_bekleyen ?? sayilar?.bekleyen ?? 0,
    onaylı: sayilar?.onaylı ?? 0,
    t30_icerisinde: !!o.t30_icerisinde
  }
}

/**
 * Rozet sözcükleri — `dil` ayarının AÇIK karşılığı (en/tr).
 *
 * ÖLÇÜLEN SORUN (18.10.2026): rozet metni yalnız uygulama yerel ayarını izliyordu; kullanıcı
 * `config.yaml → offpeak-bekci.dil: tr` yazsa bile İngilizce uygulamada rozet İngilizce kalıyordu.
 * Artık `dil` beyan edilmişse rozet o dili kullanır; boş/geçersizse eski davranış (i18n) korunur.
 */
export const ROZET_DIZGISI = {
  en: {
    rozet: pencere => (pencere === 'peak' ? 'off-peak in' : 'off-peak'),
    tip: (geri, bekleyen, onayli, kaynak) =>
      `Next window change in ${geri} · queue ${bekleyen} pending / ${onayli} approved. ${kaynak}`,
    tiklama: (pencere, geri, bekleyen, onayli) =>
      `${pencere} · change in ${geri} · queue ${bekleyen} pending / ${onayli} approved`
  },
  tr: {
    rozet: pencere => (pencere === 'peak' ? 'off-peak:' : 'off-peak'),
    tip: (geri, bekleyen, onayli, kaynak) =>
      `Pencere değişimine ${geri} · kuyruk ${bekleyen} bekliyor / ${onayli} onaylı. ${kaynak}`,
    tiklama: (pencere, geri, bekleyen, onayli) =>
      `${pencere} · değişime ${geri} · kuyruk ${bekleyen} bekliyor / ${onayli} onaylı`
  }
}

/** `dil` ayarını 'en' | 'tr' | null (tanınmayan/boş → i18n'e bırak) olarak çözer. */
export function rozetDilSec(dil) {
  const k = String(dil ?? '').trim().toLowerCase()
  return k === 'en' || k === 'tr' ? k : null
}

// ── /GÖMÜLÜ ÇEKİRDEK ──

/** Başlık çubuğuna da rozet konsun mu?
 *
 * ÖLÇÜLDÜ (hermes-agent `apps/desktop/src/app/shell/titlebar-controls.tsx:154-159`):
 * `titleBar.*` alanları **sayfa sahipliği** için kullanılır —
 * `titleBarLeft.length + titleBarRight.length > 0` ise uygulama "sayfa başlık
 * çubuğunu sahipleniyor" moduna geçer ve sabit kümeler gizlenir. Kalıcı bir
 * eklenti katkısı bu bayrağı sürekli True yapar; bu yüzden varsayılan KAPALI.
 * Açmak isteyene: aşağıdaki bayrağı true yap (uygulamanın başlık çubuğu modu değişir).
 */
const TITLEBAR_ROZET = false

let ctxRef = null
let ayar = { ...VARSAYILAN_AYAR }

/** Modül düzeyi reaktif durum: rozet bileşeni bunu izler, zamanlayıcı yazar. */
const $durum = atom(null)

/** İlk turda ölçülen kuyruk sayıları; backend yanıtı gelene kadar son bilinen değer. */
let sonSayilar = { bekleyen: 0, onaylı: 0, toplam: 0 }

/** `ctx.storage` (host) ya da bellek yedeği — `t30Karari` yalnız get/set bekler. */
function depoYap(ctx) {
  const yedek = new Map()

  return {
    get(k, d) {
      try {
        const v = ctx?.storage?.get?.(k, d)

        return v === undefined ? d : v
      } catch {
        return yedek.has(k) ? yedek.get(k) : d
      }
    },
    set(k, v) {
      try {
        ctx?.storage?.set?.(k, v)

        return
      } catch {
        yedek.set(k, v)
      }
    }
  }
}

let depo = null

/** Yanıttan JSON gövdesini çıkarır (`slash.exec` çıktısı sarılı gelebilir). */
export function jsonBul(yanit) {
  const ham = typeof yanit === 'string' ? yanit : yanit?.result ?? yanit?.output ?? yanit

  if (typeof ham !== 'string') {
    return null
  }
  const m = /\{[\s\S]*\}/.exec(ham)

  if (!m) {
    return null
  }
  try {
    return JSON.parse(m[0])
  } catch {
    return null
  }
}

/** Backend `/offpeak-durum` yanıtından kuyruk sayılarını çıkarır (defansif). */
export function yanitCoz(yanit) {
  const veri = jsonBul(yanit)

  if (!veri) {
    return null
  }

  // Yanıt şekli değişirse (üst düzey, `kuyruk`, `kuyruk_sayilari`, iç içe) kendimiz buluruz.
  const bulunan = derinKuyrukBul(veri, 0)

  if (!bulunan) {
    return null
  }

  return { bekleyen: bulunan.onay_bekleyen ?? bulunan.bekleyen ?? 0, onaylı: bulunan['onaylı'] ?? 0, toplam: bulunan.toplam }
}

/** Aynı yanıttan backend'in beyan ettiği ETKİN ayarları çıkarır (yoksa null).
 *
 * Backend `ayar` alanı `bekci_core.etkin_ayarlar()` çıktısıdır (13 ortak ayar + `varsayilanlar`
 * + `schedule_gecerli`); `ayarlariBirlestir` yalnız beyan edilen anahtarları alır.
 */
export function ayarCoz(yanit) {
  const veri = jsonBul(yanit)

  if (!veri) {
    return null
  }

  return derinAyarBul(veri, 0)
}

function derinAyarBul(dugum, derinlik) {
  if (!dugum || typeof dugum !== 'object' || derinlik > 4) {
    return null
  }
  if (dugum.varsayilanlar && typeof dugum.varsayilanlar === 'object') {
    return dugum // `etkin_ayarlar()` imzası: ayar sözlüğü + varsayılanlar
  }
  for (const deger of Object.values(dugum)) {
    const bulunan = derinAyarBul(deger, derinlik + 1)

    if (bulunan) {
      return bulunan
    }
  }

  return null
}

function derinKuyrukBul(dugum, derinlik) {
  if (!dugum || typeof dugum !== 'object' || derinlik > 4) {
    return null
  }
  if (Number.isFinite(dugum.toplam) && (dugum.bekleyen !== undefined || dugum['onaylı'] !== undefined)) {
    return dugum
  }
  for (const deger of Object.values(dugum)) {
    const bulunan = derinKuyrukBul(deger, derinlik + 1)

    if (bulunan) {
      return bulunan
    }
  }

  return null
}

/** Bir tur: saf hesaplama + T-30 kararı (+ gerekirse toast). */
function tikle() {
  const simdi = Date.now()
  const o = ozet(simdi, ayar)

  $durum.set({ ozet: o, sayilar: sonSayilar })

  const karar = t30Karari(simdi, depo, ayar)

  if (!karar.gerekli) {
    return
  }
  host.notify({
    kind: 'info',
    title: 'off-peak-bekci',
    message: `Off-peak penceresi ${o.geri_sayim} sonra açılıyor · kuyruk ${sonSayilar.bekleyen} bekliyor / ${sonSayilar['onaylı']} onaylı`
  })
  depo.set(karar.anahtar, true)
}

/** Kuyruk sayılarını backend'den tazeler (başarısızsa son değer korunur).
 *
 * ÖLÇÜLDÜ (16.10.2026 08:02/08:37, `~/.hermes/logs/agent.log`): `slash.exec` oturuma
 * bağlı bir RPC'dir (`tui_gateway/server.py` "session-scoped RPC rejected … not in
 * memory"). `session_id` gönderilmezse gateway isteği reddeder ve rozet sonsuza dek
 * yerel `0/0` değerinde kalır. Bu yüzden odaklı oturumun runtime kimliği geçilir
 * (SDK: `host.state.focusedSessionId`, bkz. desktop-plugin-sdk.md).
 */
async function sayilariTazele() {
  const sid = (() => {
    try {
      return host.state?.focusedSessionId?.get?.() ?? null
    } catch {
      return null
    }
  })()

  if (!sid) {
    return // odaklı oturum yok: RPC'yi hiç denemeyiz, son bilinen sayılar kalır
  }

  try {
    // `json` argümanı ŞART: komut varsayılan olarak İNSAN OKUR rapor döner (16.10.2026 değişikliği).
    const yanit = await host.request('slash.exec', { session_id: sid, command: 'offpeak-durum json' })
    const yeni = yanitCoz(yanit)
    const uzakAyar = ayarCoz(yanit)

    // Backend etkin ayarları (config.yaml + plugin ayarları) beyan eder: rozet onları izler,
    // böylece kullanıcı eşiği değiştirdiğinde masaüstü yarısı da aynı davranışa geçer.
    if (uzakAyar) {
      const yerel = ctxRef && typeof ctxRef.config === 'object' ? ctxRef.config : null

      ayar = ayarlariBirlestir(yerel, uzakAyar)
      // Son beyanı `ctx.storage`a yaz: eklenti yeniden yüklenirse backend yanıtı gelene
      // kadar rozet aynı eşiklerle çizilir (ayar yalnız burada, ayrı kopya tutulmaz).
      try {
        depo?.set?.('ayar', ayar)
      } catch {
        /* depo yok: yerel hesapla devam */
      }
    }
    if (yeni) {
      sonSayilar = yeni
    }
    if (yeni || uzakAyar) {
      tikle()
    }
  } catch {
    /* gateway yok/ağ kapalı: yerel hesap rozeti yine çizer */
  }
}

function Rozet() {
  const tHam = usePluginI18n(ID)
  // `dil` açıkça beyan edilmişse (en/tr) rozet o dili kullanır; değilse uygulama yerel ayarı.
  const dilKod = rozetDilSec(ayar && ayar.dil)
  const t = dilKod ? (anahtar, ...arg) => ROZET_DIZGISI[dilKod][anahtar](...arg) : tHam
  const d = useValue($durum)

  if (!d) {
    return null
  }
  const p = rozetParcalari(d.ozet, d.sayilar)
  const etiket = `${t('rozet', p.pencere)} ${p.geri_sayim}`

  return jsx(Tip, {
    label: t('tip', p.geri_sayim, p.bekleyen, p['onaylı'], KAYNAK),
    children: jsxs('button', {
      className: cn(
        'inline-flex h-full items-center gap-1 px-1.5 text-[0.6875rem] transition-colors',
        p.pencere === 'peak'
          ? 'text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground'
          : 'text-(--ui-text-secondary) hover:bg-(--chrome-action-hover) hover:text-foreground'
      ),
      type: 'button',
      onClick: () => {
        tikle()
        void sayilariTazele()
        host.notify({
          kind: 'info',
          title: 'off-peak-bekci',
          message: t('tiklama', p.pencere, p.geri_sayim, p.bekleyen, p['onaylı'])
        })
      },
      children: [
        jsx('span', { className: 'text-(--ui-text-quaternary)', children: p.pencere === 'peak' ? '☀' : '☾' }),
        jsx('span', { className: 'font-medium text-foreground', children: etiket }),
        jsx('span', {
          className: 'text-(--ui-text-quaternary)',
          children: `${p.bekleyen}/${p['onaylı']}`
        })
      ]
    })
  })
}

export default {
  id: ID, // klasör adıyla aynı olmalı
  name: 'Off-peak Bekçi',
  description: 'Ollama off-peak penceresini ve bekleyen iş kuyruğunu gösterir; pencere açılmadan önce uyarır.',
  defaultEnabled: true,
  register(ctx) {
    ctxRef = ctx
    depo = depoYap(ctx)
    try {
      // Ayar sırası: varsayılan → ctx.storage (son oturumun backend beyanı) → ctx.config
      // → backend `/offpeak-durum` yanıtı (aşağıda `sayilariTazele` içinde).
      const onceki = depo.get('ayar', null)

      ayar = ayarlariBirlestir(onceki, typeof ctx.config === 'object' ? ctx.config : null)
    } catch {
      ayar = { ...VARSAYILAN_AYAR }
    }

    // Kendi dizgileri (core en.ts düzenlenmez); app yerel ayarına göre çözülür.
    ctx.i18n.register({
      en: {
        rozet: pencere => (pencere === 'peak' ? 'off-peak in' : 'off-peak'),
        tip: (geri, bekleyen, onayli, kaynak) =>
          `Next window change in ${geri} · queue ${bekleyen} pending / ${onayli} approved. ${kaynak}`,
        tiklama: (pencere, geri, bekleyen, onayli) =>
          `${pencere} · change in ${geri} · queue ${bekleyen} pending / ${onayli} approved`
      },
      tr: {
        rozet: pencere => (pencere === 'peak' ? 'off-peak:' : 'off-peak'),
        tip: (geri, bekleyen, onayli, kaynak) =>
          `Pencere değişimine ${geri} · kuyruk ${bekleyen} bekliyor / ${onayli} onaylı. ${kaynak}`,
        tiklama: (pencere, geri, bekleyen, onayli) =>
          `${pencere} · değişime ${geri} · kuyruk ${bekleyen} bekliyor / ${onayli} onaylı`
      }
    })

    // Kalıcı çip: durum çubuğunun sağı (uygulamanın DATA/render yüzeyi).
    ctx.register({
      id: 'offpeak-rozet',
      area: STATUSBAR_AREAS.right,
      order: 40,
      render: () => jsx(Rozet, {})
    })

    if (TITLEBAR_ROZET) {
      ctx.register({
        id: 'offpeak-rozet-titlebar',
        area: TITLEBAR_AREAS.right,
        order: 40,
        render: () => jsx(Rozet, {})
      })
    }

    tikle() // ilk boyama: rozet beklemeden dolu gelsin
    ctx.setInterval(tikle, ayar.tik_ms)
    ctx.setTimeout(() => void sayilariTazele(), 2000)
    ctx.onDispose(() => {
      ctxRef = null
      depo = null
    })
  }
}

// ÜRETİLDİ: node tools/build-desktop.mjs — bu dosyayı elle düzenlemeyin.
