#!/usr/bin/env node
/**
 * `desktop/kabuk.js` + `desktop/bekci-cekirdek.js` → `desktop/plugin.js` (tek dosya).
 *
 * Neden: Hermes masaüstü host'u bir eklenti dosyasında YALNIZ
 * `@hermes/plugin-sdk`, `react`, `react/jsx-runtime` specifier'larını çözer;
 * göreli import (./bekci-cekirdek.js) yüklemeyi düşürür. Pencere matematiğini
 * yine de `node --test` ile sınayabilmek için çekirdek saf bir dosyada durur ve
 * derleme adımında gömülür.
 *
 * Kullanım:
 *   node tools/build-desktop.mjs           # üret
 *   node tools/build-desktop.mjs --check    # üretilen dosya güncel mi? (drift testi)
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const kok = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const kabukYolu = resolve(kok, 'desktop/kabuk.js')
const cekirdekYolu = resolve(kok, 'desktop/bekci-cekirdek.js')
const ciktiYolu = resolve(kok, 'desktop/plugin.js')
const ISARET = '/* __CEKIRDEK__ */'

const kabuk = readFileSync(kabukYolu, 'utf8')
const cekirdek = readFileSync(cekirdekYolu, 'utf8')

if (!kabuk.includes(ISARET)) {
  console.error(`kabuk.js içinde ${ISARET} işareti yok`)
  process.exit(2)
}

const cekirdekGovdesi = cekirdek

const uretilen = `${kabuk.replace(
  ISARET,
  `// ── GÖMÜLÜ ÇEKİRDEK (kaynak: desktop/bekci-cekirdek.js — elle düzenlemeyin) ──\n${cekirdekGovdesi}\n// ── /GÖMÜLÜ ÇEKİRDEK ──`
)}\n// ÜRETİLDİ: node tools/build-desktop.mjs — bu dosyayı elle düzenlemeyin.\n`

if (process.argv.includes('--check')) {
  let mevcut = ''
  try {
    mevcut = readFileSync(ciktiYolu, 'utf8')
  } catch {
    console.error('desktop/plugin.js yok — `node tools/build-desktop.mjs` çalıştırın')
    process.exit(1)
  }
  if (mevcut !== uretilen) {
    console.error('desktop/plugin.js BAYAT — `node tools/build-desktop.mjs` çalıştırın')
    process.exit(1)
  }
  console.log('desktop/plugin.js güncel ✓')
  process.exit(0)
}

mkdirSync(dirname(ciktiYolu), { recursive: true })
writeFileSync(ciktiYolu, uretilen)
console.log(`yazıldı: desktop/plugin.js (${uretilen.length} bayt)`)
