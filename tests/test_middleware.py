"""``llm_execution`` middleware'i için davranış testi (kuru koşu kapısı).

Neden ayrı dosya: ``bekci_core`` saftır ve ayrı test edilir; burada ise eklenti paketi
(``__init__.py``) üzerinden **middleware** sınanır: gerçekten ``time.sleep`` çağrılıyor mu?
Kapı "kuru" iken çağrılmaması, şartname §5/E5'in test edilebilir karşılığıdır.

Test hermetiktir: canlı ``config.yaml`` okunmaz (ayarlar ``ctx`` ile verilir), günlük geçici
dizine yazılır, enjekte edilen saat/patch'ler ``finally`` ile geri alınır. Ayrıntılı ölçüm
raporu: ``tools/kuru_kosu_olcum.py``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "offpeak_bekci_test", KOK / "__init__.py", submodule_search_locations=[str(KOK)]
)
assert _spec is not None and _spec.loader is not None
mod = importlib.util.module_from_spec(_spec)
sys.modules["offpeak_bekci_test"] = mod
_spec.loader.exec_module(mod)

core = mod.core
PEAK_AN = core._dt.datetime(2026, 10, 19, 13, 0, 0, tzinfo=core._dt.timezone.utc)
BULUT = dict(provider="ollama-cloud", base_url="https://ollama.com/v1", model="gpt-oss:120b")


class SahteBaglam:
    def __init__(self, **ayarlar):
        self.ayarlar = ayarlar

    def get_config(self, anahtar, varsayilan=None):
        return self.ayarlar.get(anahtar, varsayilan)


class MiddlewareTest(unittest.TestCase):
    def setUp(self):
        self.gecici = Path(tempfile.mkdtemp(prefix="offpeak-test-"))
        self._ozgun_utc = core.utc
        self._ozgun_uyku = time.sleep
        self.uykular: list[float] = []
        # `core.utc` saat değil normalleştiricidir: argümansız çağrı = şimdi.
        core.utc = lambda simdi=None: PEAK_AN if simdi is None else self._ozgun_utc(simdi)
        time.sleep = lambda sn: self.uykular.append(float(sn))
        mod._ayar_onbellek["ts"] = 0.0
        mod._sayac.sifirla()
        mod._kota_sayac.sifirla()

    def tearDown(self):
        core.utc = self._ozgun_utc
        time.sleep = self._ozgun_uyku
        mod._ayar_onbellek["ts"] = 0.0
        mod._sayac.sifirla()
        mod._kota_sayac.sifirla()

    def _kosum(self, n: int, ad: str, **ayarlar):
        gunluk = self.gecici / f"{ad}.jsonl"
        mw = mod._gecikme_kapisi(SahteBaglam(olcum_dosyasi=str(gunluk), **ayarlar))
        for i in range(n):
            mw({"i": i}, lambda req: "OK", **BULUT)
        if not gunluk.exists():
            return []
        return [json.loads(s) for s in gunluk.read_text(encoding="utf-8").splitlines() if s.strip()]

    def test_kuru_kosuda_uyku_yok_ama_olcum_var(self):
        """kuru_kosu=True: 20 istekte uyku 0; gerekli bekleme yine de hesaplanıp kaydedilir."""
        kayitlar = self._kosum(20, "kuru", kuru_kosu=True, hedef_hiz_dk=15, erteleme_tavani_sn=600.0)
        self.assertEqual(self.uykular, [])
        self.assertTrue(kayitlar, "kuru koşuda da ölçüm satırı yazılmalı")
        son = kayitlar[-1]
        self.assertEqual(son["kuru_kosu"], True)
        self.assertEqual(son["uygulanacak_sn"], 0.0)
        self.assertGreater(son["gerekli_sn"], 0.0)  # kapı hesap yaptı, sadece uyumadı
        self.assertEqual(son["hedef_hiz_dk"], 15)  # ctx ayarı middleware'e ulaştı
        self.assertEqual(son["tavan_sn"], 600.0)

    def test_kuru_kosu_kapaliyken_uyku_istenir(self):
        """Kontrol: kuru_kosu=False → aynı yükte uyku istenir (kapı ölü değil)."""
        kayitlar = self._kosum(20, "canli", kuru_kosu=False, hedef_hiz_dk=15, erteleme_tavani_sn=600.0)
        self.assertEqual(len(self.uykular), 5)  # 20 çağrı - 15 hedef = 5 fazla
        self.assertTrue(all(sn > 0 for sn in self.uykular))
        self.assertEqual(kayitlar[-1]["uygulanacak_sn"], self.uykular[-1])

    def test_yerel_ollamaya_dokunulmaz(self):
        """Yerel/LAN Ollama'da pencere kavramı yok → hiç ölçüm/uyku olmamalı."""
        gunluk = self.gecici / "yerel.jsonl"
        mw = mod._gecikme_kapisi(SahteBaglam(olcum_dosyasi=str(gunluk)))
        for i in range(10):
            mw({"i": i}, lambda req: "OK", base_url="http://192.168.1.9:11434", model="qwen3:8b")
        self.assertEqual(self.uykular, [])
        self.assertFalse(gunluk.exists(), "yerel çağrı günlüğe bile yazılmamalı")


if __name__ == "__main__":
    unittest.main()
