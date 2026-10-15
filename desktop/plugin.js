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
export const T30_DK = 30

/** Rozet başlığında gösterilen kaynak cümlesi. */
export const KAYNAK =
  'Ollama: "Off-peak pricing apply outside 12:00 and 18:00 UTC on weekdays and all day on weekends."'

export const VARSAYILAN_AYAR = {
  t30_dk: T30_DK,
  tik_ms: 30_000,
  geri_sayim_esigi_sn: 12 * 60 * 60,
  kuyruk_dosyasi: '~/MacAir/off-peak-kuyruk.md'
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

/** Off-peak'e `t30Dk` dakika veya daha az kaldıysa true (yalnız peak'te). */
export function t30Icerisinde(ms, t30Dk = T30_DK) {
  if (!peakMi(ms)) {
    return false
  }

  return kalanSaniye(ms) <= Math.max(0, Math.trunc(t30Dk)) * 60
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
  const t30Dk = Number.isFinite(ayar?.t30_dk) ? ayar.t30_dk : T30_DK
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

  if (!t30Icerisinde(ms, ayar?.t30_dk ?? T30_DK)) {
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
  x: ONAYLI,
  bekliyor: BEKLIYOR,
  'onay-bekliyor': BEKLIYOR,
  'onay bekliyor': BEKLIYOR,
  'onay-beklemede': BEKLIYOR,
  beklemede: BEKLIYOR,
  pending: BEKLIYOR,
  open: BEKLIYOR,
  taslak: BEKLIYOR
}

const TABLO_BASLIKLARI = new Set([
  'id', 'iş', 'is', 'kalem', 'sahip', 'owner', 'kanıt', 'kanit', 'kanıt/dosya',
  'durum', 'status', 'pencere', 'efor', 'effort', 'not', 'notlar', 'başlık', 'baslik'
])

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

/** `| a | b |` satırını hücrelere çözer; tablo değilse/ayraçsa null. */
function tabloHucreleri(satir) {
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
  if (!hucreler.length) {
    return null
  }
  if (hucreler.every(h => TABLO_AYRAC_HUCRE.test(h.ham.trim()) || !h.ham.trim())) {
    return null
  }

  return { ic, hucreler }
}

/** Tek satırı kaleme çevirir; kalem değilse null. */
export function kalemAyristir(satir, no = 0) {
  const tablo = tabloHucreleri(satir)

  if (tablo) {
    const { hucreler } = tablo
    const temiz = hucreler.map(h => temizle(h.ham))
    const dolu = temiz.filter(Boolean)

    if (!dolu.length || dolu.every(t => TABLO_BASLIKLARI.has(t.toLowerCase()))) {
      return null
    }
    const kidHam = temiz.find(t => TABLO_ID.test(t))

    if (!kidHam || hucreler.length < 4) {
      return null
    }
    const durumHam = temiz.find(t => DURUM_ESANLAMLILARI[t.toLowerCase()] !== undefined)
    const eforHam = temiz.find(t => TABLO_EFOR.test(t))

    return {
      id: kidHam.replace(/`/g, ''),
      durum: durumHam ? DURUM_ESANLAMLILARI[durumHam.toLowerCase()] : BEKLIYOR,
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

  for (let i = 0; i < satirlar.length; i += 1) {
    const kalem = kalemAyristir(satirlar[i].replace(/\r$/, ''), i + 1)

    if (kalem) {
      kalemler.push(kalem)
    }
  }

  return kalemler
}

/** `{bekleyen, onaylı, beklemede, koşuldu, atlandı, sahipsiz, toplam}` (Python ile aynı). */
export function kuyrukSayilari(kalemler) {
  const liste = Array.isArray(kalemler) ? kalemler : []
  const onayli = liste.filter(k => k?.durum === ONAYLI).length
  const beklemede = liste.filter(k => k?.durum === BEKLIYOR).length

  return {
    bekleyen: liste.length - onayli,
    onaylı: onayli,
    beklemede,
    'koşuldu': liste.filter(k => k?.durum === 'koşuldu').length,
    'atlandı': liste.filter(k => k?.durum === 'atlandı').length,
    sahipsiz: liste.filter(k => k?.durum === 'sahipsiz').length,
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
    bekleyen: sayilar?.bekleyen ?? 0,
    onaylı: sayilar?.onaylı ?? 0,
    t30_icerisinde: !!o.t30_icerisinde
  }
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

/** Backend `/offpeak-durum` yanıtından kuyruk sayılarını çıkarır (defansif). */
export function yanitCoz(yanit) {
  const ham = typeof yanit === 'string' ? yanit : yanit?.result ?? yanit?.output ?? yanit

  if (typeof ham !== 'string') {
    return null
  }
  const m = /\{[\s\S]*\}/.exec(ham)

  if (!m) {
    return null
  }
  let veri = null

  try {
    veri = JSON.parse(m[0])
  } catch {
    return null
  }

  // Yanıt şekli değişirse (üst düzey, `kuyruk`, `kuyruk_sayilari`, iç içe) kendimiz buluruz.
  const bulunan = derinKuyrukBul(veri, 0)

  if (!bulunan) {
    return null
  }

  return { bekleyen: bulunan.bekleyen ?? 0, onaylı: bulunan['onaylı'] ?? 0, toplam: bulunan.toplam }
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

/** Kuyruk sayılarını backend'den tazeler (başarısızsa son değer korunur). */
async function sayilariTazele() {
  try {
    const yanit = await host.request('slash.exec', { command: 'offpeak-durum' })
    const yeni = yanitCoz(yanit)

    if (yeni) {
      sonSayilar = yeni
      tikle()
    }
  } catch {
    /* gateway yok/ağ kapalı: yerel hesap rozeti yine çizer */
  }
}

function Rozet() {
  const t = usePluginI18n(ID)
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
      ayar = { ...VARSAYILAN_AYAR, ...(typeof ctx.config === 'object' && ctx.config ? ctx.config : {}) }
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
