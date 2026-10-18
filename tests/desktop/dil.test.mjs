/**
 * Rozet dili: `dil` ayarı (en/tr) rozet sözcüklerini belirler; boş/geçersiz → i18n (uygulama yerel ayarı).
 * Çalıştırma: `node --test tests/desktop/`
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { ROZET_DIZGISI, rozetDilSec } from '../../desktop/bekci-cekirdek.js'

test('rozetDilSec: en/tr tanınır, boş ve bilinmeyen null', () => {
  assert.equal(rozetDilSec('tr'), 'tr')
  assert.equal(rozetDilSec('TR'), 'tr')
  assert.equal(rozetDilSec(' en '), 'en')
  assert.equal(rozetDilSec(''), null)
  assert.equal(rozetDilSec(undefined), null)
  assert.equal(rozetDilSec('de'), null)
})

test('dil: tr → rozet sözcükleri Türkçe, en → İngilizce', () => {
  assert.match(ROZET_DIZGISI.tr.tip('01:20', 3, 1, 'kaynak'), /Pencere değişimine 01:20 · kuyruk 3 bekliyor \/ 1 onaylı/)
  assert.match(ROZET_DIZGISI.en.tip('01:20', 3, 1, 'src'), /Next window change in 01:20 · queue 3 pending \/ 1 approved/)
  assert.equal(ROZET_DIZGISI.tr.rozet('peak'), 'off-peak:')
  assert.equal(ROZET_DIZGISI.en.rozet('peak'), 'off-peak in')
  assert.equal(ROZET_DIZGISI.tr.rozet('off-peak'), ROZET_DIZGISI.en.rozet('off-peak'))
})

test('iki dil aynı anahtar kümesini taşır (eksik çeviri sessizce geçmez)', () => {
  assert.deepEqual(Object.keys(ROZET_DIZGISI.tr).sort(), Object.keys(ROZET_DIZGISI.en).sort())
})
