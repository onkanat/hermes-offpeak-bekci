"""Kuyruk tüketicisi sayacı + "tüketici yok" uyarısı (issue #3).

Neyi kanıtlar (ölçüldü 23.10.2026):
  * Kuyrukta **onaylı** kalem varken iki tüketici de `enabled: false` idi ve hiçbir
    uyarı çıkmıyordu; arıza ancak `~/.hermes/cron/jobs.json` elle okununca görüldü.
  * `/offpeak-durum` artık tüketici sayısını (`tuketici`) taşır ve onaylı kalem varken
    **etkin tüketici 0** ise özete "KOŞMAZ" uyarısını ekler.
  * Desen eşleşmezse (yabancı iş adları) hüküm VERİLMEZ — yanlış alarm, sessizlikten
    daha pahalıdır (bkz. `bekci_core.tuketici_sayaci` docstring'i).

Hermetik: `_ayarlar`, `_kuyruk_oku`, `_kurulum_isleri_oku` sabitlerle değiştirilir;
gerçek config/cron dosyası okunmaz.
Çalıştırma: `~/.hermes/hermes-agent/venv/bin/python3 -m unittest discover -s tests -t . -v`
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest
from typing import Any

KOK = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

import bekci_core as c  # noqa: E402


def _modul() -> Any:
    spec = importlib.util.spec_from_file_location(
        "offpeak_bekci_tuketici_test", KOK / "__init__.py", submodule_search_locations=[str(KOK)]
    )
    assert spec is not None and spec.loader is not None
    pkg = importlib.util.module_from_spec(spec)
    sys.modules["offpeak_bekci_tuketici_test"] = pkg
    spec.loader.exec_module(pkg)
    return pkg


#: 23.10.2026'daki gerçek `jobs.json` şekli (kısaltılmış): iki tüketici de KAPALI.
ISLER_GERCEK = [
    {"id": "6068be9517a2", "name": "offpeak-kuyruk-kosusu (bekci kapili)", "enabled": False,
     "monitor_script": "offpeak_bekci.py"},
    {"id": "82d98e06034a", "name": "offpeak-kuyruk-kosusu (agy · 0 token)", "enabled": False,
     "script": "offpeak_agy_kosusu.py"},
    {"id": "e000937c5583", "name": "offpeak-urun-nabiz (haftalik)", "enabled": True,
     "script": "offpeak_urun_nabiz.py"},
    {"id": "60df87426577", "name": "offpeak-issue-taslak (15 dk)", "enabled": True},
    {"id": "697ca1d40c6c", "name": "cadbridge-offpeak-dalga", "enabled": True,
     "script": "cadbridge_gece.py"},
]

KALEMLER_ONAYLI = [
    {"id": "K-042", "durum": "koşuldu", "metin": "eski iş"},
    {"id": "K-043", "durum": "onaylı", "metin": "K-043 — ressam profili · onaylı"},
]


class TuketiciSayaciTest(unittest.TestCase):
    """`tuketici_sayaci` — saf fonksiyon, yalnız verilen iş listesini okur."""

    def test_gercek_sekil_iki_tuketici_de_kapali(self):
        t = c.tuketici_sayaci(ISLER_GERCEK)
        self.assertEqual((t["etkin"], t["toplam"]), (0, 2))
        self.assertEqual({k["id"] for k in t["isler"]}, {"6068be9517a2", "82d98e06034a"})
        self.assertTrue(all(k["etkin"] is False for k in t["isler"]))

    def test_tuketici_olmayan_isler_sayilmaz(self):
        """Nabız/taslak/cadbridge işleri tüketici DEĞİL — yanlış sayım uyarıyı bastırırdı."""
        t = c.tuketici_sayaci(ISLER_GERCEK)
        adlar = {k["ad"] for k in t["isler"]}
        self.assertNotIn("offpeak-urun-nabiz (haftalik)", adlar)
        self.assertNotIn("offpeak-issue-taslak (15 dk)", adlar)
        self.assertNotIn("cadbridge-offpeak-dalga", adlar)

    def test_bir_tuketici_acilinca_etkin_artar(self):
        isler = [dict(i, enabled=True) if i["id"] == "82d98e06034a" else dict(i) for i in ISLER_GERCEK]
        t = c.tuketici_sayaci(isler)
        self.assertEqual((t["etkin"], t["toplam"]), (1, 2))

    def test_desen_yoksa_hukum_yok(self):
        """Boş desen listesi → toplam 0 (çağıran 'tüketici yok' hükmü vermez)."""
        self.assertEqual(c.tuketici_sayaci(ISLER_GERCEK, desenler=[]),
                         {"etkin": 0, "toplam": 0, "isler": []})

    def test_bilinmeyen_is_adlari_hukum_uretmez(self):
        """Farklı adlandırma kullanan makinede yanlış alarm çıkmaz."""
        t = c.tuketici_sayaci([{"id": "x", "name": "benim-iscim", "enabled": True}])
        self.assertEqual(t["toplam"], 0)

    def test_bozuk_girdi_cokmez(self):
        self.assertEqual(c.tuketici_sayaci(None)["toplam"], 0)
        self.assertEqual(c.tuketici_sayaci([None, "metin", 7])["toplam"], 0)


class DurumCiktisiTest(unittest.TestCase):
    """`/offpeak-durum` çıktısında tüketici alanı ve uyarı."""

    def setUp(self):
        self.pkg = _modul()
        self._yedek = (self.pkg._ayarlar, self.pkg._kuyruk_oku, self.pkg._kurulum_isleri_oku)
        self.pkg._ayarlar = lambda ctx=None: dict(c.VARSAYILAN_AYARLAR, kuru_kosu=True, dil="en")

    def tearDown(self):
        self.pkg._ayarlar, self.pkg._kuyruk_oku, self.pkg._kurulum_isleri_oku = self._yedek

    def _kos(self, kalemler, isler, dil="en"):
        self.pkg._ayarlar = lambda ctx=None: dict(c.VARSAYILAN_AYARLAR, kuru_kosu=True, dil=dil)
        self.pkg._kuyruk_oku = lambda ayar: (kalemler, None)
        self.pkg._kurulum_isleri_oku = lambda dil_="en": (isler, None)
        return self.pkg._durum_verisi(None)

    def test_onayli_var_tuketici_yok_uyari(self):
        d = self._kos(KALEMLER_ONAYLI, ISLER_GERCEK)
        self.assertEqual(d["kuyruk"]["onaylı"], 1)
        self.assertEqual(d["tuketici"]["etkin"], 0)
        self.assertTrue(d["tuketici_uyari"])
        self.assertIn("WON'T RUN", d["ozet"])
        # İnsan raporu da aynı hükmü yazmalı (kullanıcı `/offpeak-durum` yazınca görür).
        rapor = self.pkg._durum_metni(d, "en")
        self.assertIn("CANNOT run", rapor)

    def test_onayli_var_tuketici_var_uyari_yok(self):
        isler = [dict(i, enabled=True) if i["id"] == "6068be9517a2" else dict(i) for i in ISLER_GERCEK]
        d = self._kos(KALEMLER_ONAYLI, isler)
        self.assertFalse(d["tuketici_uyari"])
        self.assertNotIn("WON'T RUN", d["ozet"])
        self.assertIn("1/2 enabled", self.pkg._durum_metni(d, "en"))

    def test_onayli_yokken_uyari_yok(self):
        d = self._kos([{"id": "K-001", "durum": "koşuldu", "metin": "bitti"}], ISLER_GERCEK)
        self.assertEqual(d["kuyruk"]["onaylı"], 0)
        self.assertFalse(d["tuketici_uyari"])
        self.assertNotIn("WON'T RUN", d["ozet"])

    def test_turkce_uyari(self):
        d = self._kos(KALEMLER_ONAYLI, ISLER_GERCEK, dil="tr")
        self.assertIn("KOŞMAZ", d["ozet"])
        self.assertIn("KOŞAMAZ", self.pkg._durum_metni(d, "tr"))

    def test_isler_okunamazsa_hukum_yok(self):
        """cron deposu okunamazsa (hata) tüketici 0 varsayılıp yanlış alarm verilmez."""
        self.pkg._ayarlar = lambda ctx=None: dict(c.VARSAYILAN_AYARLAR, kuru_kosu=True, dil="en")
        self.pkg._kuyruk_oku = lambda ayar: (KALEMLER_ONAYLI, None)
        self.pkg._kurulum_isleri_oku = lambda dil_="en": ([], "okunamadı")
        d = self.pkg._durum_verisi(None)
        self.assertEqual(d["tuketici"]["toplam"], 0)
        self.assertFalse(d["tuketici_uyari"])
        self.assertEqual(d["tuketici_hata"], "okunamadı")

    def test_mevcut_anahtarlar_bozulmadi(self):
        """Sözleşme: yalnız EKLEME — eski anahtarlar ve sayılar aynı kalmalı."""
        d = self._kos(KALEMLER_ONAYLI, ISLER_GERCEK)
        for anahtar in ("pencere", "peak_mi", "gelecek_pencere", "geri_sayim", "t30_icerisinde",
                        "ozet", "kuyruk", "kalemler", "kuru_kosu", "hedef_hiz_dk",
                        "erteleme_tavani_sn", "son_60sn", "kota", "ayar", "kuyruk_dosyasi"):
            self.assertIn(anahtar, d)
        self.assertEqual(d["kuyruk"]["toplam"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
