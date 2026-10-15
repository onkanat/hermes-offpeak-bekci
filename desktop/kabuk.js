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

/* __CEKIRDEK__ */

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
