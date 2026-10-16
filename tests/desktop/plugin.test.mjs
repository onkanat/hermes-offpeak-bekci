/**
 * Masaüstü KABUĞU davranış testi (W4a-2 kanıtı): gerçek `desktop/plugin.js` çıktısı,
 * sahte `@hermes/plugin-sdk` + `react/jsx-runtime` ile yüklenir; `ctx`/`host` sahteleri
 * üzerinden rozetin **hangi ayarı ve hangi sayıları** çizdiği ölçülür.
 *
 * Ayar okuyucu zinciri (kabuk.js): varsayılan → `ctx.storage` (son backend beyanı)
 * → `ctx.config` → `/offpeak-durum` yanıtı (`ayar` + `kuyruk`). Bu test zincirin
 * ölçülebilir ucunu sabitler; "o dosyadan okuyor" iddiasının masaüstü tarafı budur.
 *
 * Fikstür `fixtures/durum-gecici-defter.json`: 16.10.2026'da CANLI olarak ölçülmüş
 * `/offpeak-durum` yanıtı — `config.yaml:offpeak-bekci.kuyruk_dosyasi` geçici test
 * defterine çevrilmişken alındı (bekleyen=3 · onaylı=1 · toplam=4). Yanıttaki mutlak
 * kullanıcı yolu `/tmp/offpeak-olcum/gecici-kuyruk.md` olarak TEMİZLENDİ (repoda
 * makineye özgü yol durmaz); başka hiçbir değer değiştirilmedi.
 *
 * Çalıştırma: `node --test tests/desktop/`
 */
import assert from 'node:assert/strict'
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { test } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'

import { ID, VARSAYILAN_AYAR } from '../../desktop/bekci-cekirdek.js'

const KOK = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..')
const FIKS = JSON.parse(
  readFileSync(join(KOK, 'tests', 'desktop', 'fixtures', 'durum-gecici-defter.json'), 'utf8')
)
/** Fikstürdeki (temizlenmiş) defter yolu — ayar katmanından gelen etkin değer. */
const FIKS_DEFTER = '/tmp/offpeak-olcum/gecici-kuyruk.md'

/** Sahte SDK: gerçek yüzeyi (`@hermes/plugin-sdk`) taklit eder, köprüden veri alır. */
const SDK_SAHTE = `
const kopru = () => globalThis.__offpeakTest
export const STATUSBAR_AREAS = { left: 'statusBar.left', right: 'statusBar.right' }
export const TITLEBAR_AREAS = { center: 'titleBar.center', left: 'titleBar.left', right: 'titleBar.right' }
export function atom(ilk) {
  const k = { v: ilk, get: () => k.v, set: (x) => { k.v = x } }
  return k
}
export function useValue(a) { return a.get() }
export function cn(...parcalar) { return parcalar.filter(Boolean).join(' ') }
export function Tip(ozellikler) { return { tip: true, label: ozellikler.label, children: ozellikler.children } }
export function usePluginI18n(id) { return (anahtar, ...arg) => kopru().cevir(id, anahtar, ...arg) }
export const host = {
  notify: (bildirim) => kopru().bildirimler.push(bildirim),
  request: (yol, arg) => kopru().istek(yol, arg),
  get state() { return kopru().hostDurum }
}
`

/** Sahte `react/jsx-runtime`: öğeyi düz nesneye çevirir (ağaç yürünebilir kalsın). */
const JSX_SAHTE = `
export function jsx(type, props, key) { return { type, props: props ?? {}, key } }
export function jsxs(type, props, key) { return { type, props: props ?? {}, key } }
export function Fragment(props) { return props.children }
`

const REACT_SAHTE = `export default { createElement: (type, props, ...cocuklar) => ({ type, props: { ...(props ?? {}), children: cocuklar } }) }\n`

/** Gerçek çıktıyı (`desktop/plugin.js`) geçici bir kurulum dizinine kopyalar. */
function kurulum() {
  const dizin = mkdtempSync(join(tmpdir(), 'offpeak-kabuk-'))
  const nm = join(dizin, 'node_modules')

  mkdirSync(join(nm, '@hermes', 'plugin-sdk'), { recursive: true })
  mkdirSync(join(nm, 'react'), { recursive: true })
  writeFileSync(
    join(nm, '@hermes', 'plugin-sdk', 'package.json'),
    JSON.stringify({ name: '@hermes/plugin-sdk', version: '0.0.0', type: 'module', main: 'index.js' })
  )
  writeFileSync(join(nm, '@hermes', 'plugin-sdk', 'index.js'), SDK_SAHTE)
  writeFileSync(
    join(nm, 'react', 'package.json'),
    JSON.stringify({
      name: 'react',
      version: '0.0.0',
      type: 'module',
      // ESM alt yol çözümü uzantı tahmin etmez: `react/jsx-runtime` eşlenmeli.
      exports: { '.': './index.js', './jsx-runtime': './jsx-runtime.js' }
    })
  )
  writeFileSync(join(nm, 'react', 'index.js'), REACT_SAHTE)
  writeFileSync(join(nm, 'react', 'jsx-runtime.js'), JSX_SAHTE)
  copyFileSync(join(KOK, 'desktop', 'plugin.js'), join(dizin, 'plugin.js'))

  return dizin
}

/** Sahte `ctx`: kayıt/timer/depo yakalar. `host` köprüsü ayrıca kurulur. */
function sahteCtx(ayar) {
  const depo = new Map()

  if (ayar?.depoBaslangic) {
    for (const [k, v] of Object.entries(ayar.depoBaslangic)) {
      depo.set(k, v)
    }
  }

  const kayitli = []
  const zaman = { interval: [], timeout: [], dispose: null }

  return {
    depo,
    kayitli,
    zaman,
    dilPaketleri: [],
    config: ayar?.config ?? {},
    storage: {
      get: (k, varsayilan) => (depo.has(k) ? depo.get(k) : varsayilan),
      set: (k, v) => {
        depo.set(k, v)
      }
    },
    i18n: {
      register: (paket) => {
        kopru().dilPaketleri.push(paket)
      }
    },
    register: (katki) => kayitli.push(katki),
    setInterval: (fn, ms) => {
      zaman.interval.push({ fn, ms })
      return zaman.interval.length
    },
    setTimeout: (fn, ms) => {
      zaman.timeout.push({ fn, ms })
      return zaman.timeout.length
    },
    onDispose: (fn) => {
      zaman.dispose = fn
    }
  }
}

let kopru = () => globalThis.__offpeakTest

/**
 * Eklentiyi sahte ctx + host ile yükler ve `register` eder.
 * @param {{config?: object, depoBaslangic?: object, odak?: string|null, istek?: Function}} secenek
 */
async function yukleVeKaydet(secenek = {}) {
  const dizin = kurulum()
  const sdk = await import(pathToFileURL(join(dizin, 'node_modules', '@hermes', 'plugin-sdk', 'index.js')).href)
  const cagrilar = []
  const bildirimler = []
  const bridge = {
    bildirimler,
    cagrilar,
    dil: 'tr',
    dilPaketleri: [],
    hostDurum: { focusedSessionId: sdk.atom(secenek.odak ?? null) },
    istek:
      secenek.istek ??
      (async (yol, arg) => {
        cagrilar.push({ yol, arg })
        return null
      }),
    cevir: (id, anahtar, ...arg) => {
      const paket = globalThis.__offpeakTest.dilPaketleri.at(-1) ?? {}
      const sozluk = paket[globalThis.__offpeakTest.dil] ?? paket.en ?? {}
      const f = sozluk[anahtar]

      return typeof f === 'function' ? f(...arg) : String(f ?? anahtar)
    }
  }

  globalThis.__offpeakTest = bridge

  const mod = await import(pathToFileURL(join(dizin, 'plugin.js')).href)
  const ctx = sahteCtx(secenek)

  mod.default.register(ctx)

  return { bridge, ctx, katki: ctx.kayitli[0], mod }
}

/** Öğe ağacındaki tüm düz metinleri toplar. */
function metin(dugum) {
  if (dugum == null) {
    return ''
  }
  if (typeof dugum === 'string' || typeof dugum === 'number') {
    return String(dugum)
  }
  if (Array.isArray(dugum)) {
    return dugum.map(metin).join(' ')
  }
  if (typeof dugum === 'function') {
    return ''
  }

  return metin(dugum.children ?? dugum.props?.children)
}

/** Kayıtlı katkının rozet ağacını çizer (bileşen elle çağrılır — sahte hooks düz fonksiyon). */
function rozetAgaci(katki) {
  const eleman = katki.render()

  return eleman.type(eleman.props)
}

test('kayıt: rozet statusBar.right alanına order 40 ile eklenir; ilk boyama 0/0', async () => {
  const { ctx, katki } = await yukleVeKaydet()

  assert.equal(ctx.kayitli.length, 1)
  assert.equal(katki.id, 'offpeak-rozet')
  assert.equal(katki.area, 'statusBar.right')
  assert.equal(katki.order, 40)

  const agac = rozetAgaci(katki)
  const yazi = metin(agac.props.children)

  assert.match(yazi, /off-peak/, 'rozet etiketi penceresini yazar')
  assert.match(yazi, /\d\d:\d\d/, 'geri sayım çizilir')
  assert.match(yazi, /0\/0/, 'backend yanıtı yokken sayaç 0/0 kalır')
  assert.match(agac.props.label, /0 bekliyor \/ 0 onaylı/, 'ipucu sayıları tr sözlükten gelir')
  assert.equal(ctx.zaman.interval[0].ms, VARSAYILAN_AYAR.tik_ms, 'tik aralığı şema varsayılanı')
  assert.equal(ctx.zaman.timeout[0].ms, 2000, 'ilk backend tazelemesi 2 sn sonra')
})

test('davranış: backend beyanı geçici defteri ve sayıları (3/1) rozete geçirir', async () => {
  const { bridge, ctx, katki } = await yukleVeKaydet({
    odak: 'oturum-w4a2',
    config: { on_bildirim_dk: 45 }, // çakışan yerel değer: backend beyanı ezmeli
    istek: async (yol, arg) => {
      bridge.cagrilar.push({ yol, arg })
      return { result: JSON.stringify(FIKS) }
    }
  })

  await ctx.zaman.timeout[0].fn()

  assert.deepEqual(bridge.cagrilar, [
    { yol: 'slash.exec', arg: { session_id: 'oturum-w4a2', command: 'offpeak-durum' } }
  ])

  const yazi = metin(rozetAgaci(katki).props.children)
  const ipucu = rozetAgaci(katki).props.label

  assert.match(yazi, /3\/1/, 'sayaç backend yanıtındaki kuyruk sayılarını yazar')
  assert.match(ipucu, /3 bekliyor \/ 1 onaylı/, 'ipucu sayıları backend beyanından')
  assert.match(ipucu, /Off-peak pricing apply outside 12:00 and 18:00 UTC/, 'kaynak metni ipucunda')

  const ayar = ctx.depo.get('ayar')

  assert.ok(ayar, 'etkin ayarlar ctx.storage’a yazılır (yeniden yükleme için)')
  assert.equal(ayar.kuyruk_dosyasi, FIKS_DEFTER, 'etkin defter = geçici test defteri')
  assert.equal(
    VARSAYILAN_AYAR.kuyruk_dosyasi,
    '~/.hermes/offpeak-bekci/kuyruk.md',
    'şema varsayılanı sabit kalır'
  )
  assert.notEqual(
    ayar.kuyruk_dosyasi,
    VARSAYILAN_AYAR.kuyruk_dosyasi,
    'etkin defter varsayılandan farklı ⇒ ayar katmanından geldi'
  )
  assert.equal(ayar.on_bildirim_dk, 30, 'backend beyanı ctx.config’i (45) ezer')
  assert.equal(ayar.hedef_hiz_dk, 15, 'backend’in etkin hedef hızı rozete geçer')
  assert.equal('varsayilanlar' in ayar, false, 'katman sözlüğü depoya sızmaz (ayarTemizle)')
})

test('yeniden yükleme: ctx.storage’daki son beyan okunur, ctx.config varsa o ezer', async () => {
  const { ctx } = await yukleVeKaydet({
    depoBaslangic: { ayar: { tik_ms: 7000, kuyruk_dosyasi: FIKS_DEFTER } },
    config: { tik_ms: 1000 }
  })

  // `ayarlariBirlestir(...)` sırayla ezer: depodaki beyan önce, ctx.config sonra
  // (kabuk.js register: `ayarlariBirlestir(onceki, ctx.config)`).
  assert.equal(ctx.zaman.interval[0].ms, 1000, 'ctx.config depodaki beyanı ezer')
  assert.equal(ctx.depo.get('ayar').tik_ms, 7000, 'okuma depoyu değiştirmez (yazma yalnız backend yanıtında)')
})

test('odaklı oturum yoksa backend’e hiç gidilmez (sayaç son değeri korur)', async () => {
  let denendi = false
  const { ctx } = await yukleVeKaydet({
    odak: null,
    istek: async () => {
      denendi = true
      return null
    }
  })

  await ctx.zaman.timeout[0].fn()
  assert.equal(denendi, false, 'focusedSessionId yokken RPC denenmez (gateway reddederdi)')
})

test('gateway yoksa rozet yine çizilir (yerel hesap, 0/0)', async () => {
  const { ctx, katki } = await yukleVeKaydet({
    odak: 'oturum-w4a2',
    istek: async () => {
      throw new Error('gateway yok')
    }
  })

  await ctx.zaman.timeout[0].fn()

  const yazi = metin(rozetAgaci(katki).props.children)

  assert.match(yazi, /0\/0/)
  assert.match(yazi, /\d\d:\d\d/)
  assert.equal(ctx.depo.get('ayar')?.kuyruk_dosyasi, undefined, 'başarısız yanıt depoya yazılmaz')
})

test('bozuk/sarılı yanıt ayarları bozmaz (jsonBul defansif)', async () => {
  const { ctx, katki } = await yukleVeKaydet({
    odak: 'oturum-w4a2',
    istek: async () => ({ result: 'gateway: komut bulunamadı (JSON yok)' })
  })

  await ctx.zaman.timeout[0].fn()

  assert.match(metin(rozetAgaci(katki).props.children), /0\/0/, 'sayılar korunur')
  assert.equal(ctx.depo.get('ayar'), undefined, 'ayar yazılmaz')
})

test('kimlik: eklenti kimliği çekirdekle aynı, katkı kimliği ayrı', async () => {
  const { katki, mod } = await yukleVeKaydet()

  assert.equal(mod.default.id, ID, 'eklenti kimliği = klasör adı (bekci-cekirdek ID)')
  assert.equal(mod.default.defaultEnabled, true)
  assert.equal(katki.id, 'offpeak-rozet', 'katkı kimliği rozet adıdır')
})
