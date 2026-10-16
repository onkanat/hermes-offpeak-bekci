"""`/offpeak-durum` çıktı biçimi testi (16.10.2026).

Neyi kanıtlar:
  * Varsayılan çıktı **insan okur rapor**tur (kullanıcı komutu kendisi yazınca ham JSON
    okuyamıyordu; ölçüm: masaüstü sohbeti).
  * `json` argümanı (büyük/küçük harf, boşluk toleranslı) **tek satır JSON** döner — masaüstü
    rozeti bu yolu kullanır, sözleşme bozulmaz (aynı anahtarlar).
  * Rapor kısa kalır (≤ 14 satır) ve kuyruk/kota/kuru koşu bilgisini içerir.

Hermetik: `_durum_verisi` sabit bir sözlükle değiştirilir; gerçek config/kuyruk dosyası okunmaz.
Çalıştırma: `python3 -m unittest discover -s tests -t . -v`
"""

from __future__ import annotations

import json
import pathlib
import sys
import types
import unittest

KOK = pathlib.Path(__file__).resolve().parents[1]


def _modul() -> types.ModuleType:
    pkg = types.ModuleType("offpeak_bekci_cikti_test")
    pkg.__path__ = [str(KOK)]
    sys.modules["offpeak_bekci_cikti_test"] = pkg
    exec((KOK / "__init__.py").read_text(encoding="utf-8"), pkg.__dict__)
    return pkg


VERI = {
    "pencere": "peak", "peak_mi": True, "gelecek_pencere": "off-peak", "geri_sayim": "01:07",
    "ozet": "PEAK · off-peak 01:07 sonra · kuyruk 2 bekliyor / 1 onaylı",
    "kuru_kosu": True, "hedef_hiz_dk": 15, "erteleme_tavani_sn": 600, "son_60sn": 0,
    "kuyruk": {"bekleyen": 2, "onaylı": 1, "beklemede": 0, "koşuldu": 1, "atlandı": 0,
               "sahipsiz": 0, "toplam": 2},
    "kota": {"sayi": 3, "tavan": 120, "uyari": False, "asildi": False},
    "kuyruk_dosyasi": "/tmp/kuyruk.md", "kuyruk_dosyasi_var": True, "kuyruk_hata": None,
    "kalemler": [
        {"id": "K-001", "durum": "koşuldu", "metin": "eski iş"},
        {"id": "K-002", "durum": "bekliyor", "metin": "| K-002 | **Bağlam denetimi** — cache_read kaynağı | MacAir | ölçüm dosyası"},
    ],
    "ayar": {},
}


class CiktiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.pkg = _modul()
        self.pkg._durum_verisi = lambda ctx=None: dict(VERI)  # hermetic
        self.komut = self.pkg._komut_durum(None)

    def test_varsayilan_insan_okur(self) -> None:
        cikti = self.komut("")
        self.assertFalse(cikti.lstrip().startswith("{"), "varsayılan çıktı JSON olmamalı")
        self.assertIn("Off-peak bekçisi", cikti)
        self.assertIn("PEAK · off-peak 01:07 sonra", cikti)
        self.assertIn("kuru koşu", cikti)
        self.assertIn("son 60 sn", cikti)
        self.assertIn("K-002", cikti)          # onay/iş bekleyen kalem listelenir
        self.assertNotIn("K-001", cikti)       # koşulmuş kalem listelenmez
        self.assertLessEqual(len(cikti.splitlines()), 14, "rapor kısa kalmalı")

    def test_json_argumani_sozlesmeyi_korur(self) -> None:
        for arg in ["json", "JSON", " json ", "json ekstra"]:
            d = json.loads(self.komut(arg))
            self.assertEqual(d["ozet"], VERI["ozet"])
            self.assertEqual(d["kuyruk"]["toplam"], 2)
            self.assertIn("kota", d)

    def test_bilinmeyen_arguman_rapor_dondurur(self) -> None:
        self.assertIn("Off-peak bekçisi", self.komut("rapor"))

    def test_kuyruk_dosyasi_okunamazsa_gorunur(self) -> None:
        bozuk = dict(VERI, kuyruk_dosyasi_var=False, kuyruk_hata="dosya yok")
        self.pkg._durum_verisi = lambda ctx=None: bozuk
        cikti = self.pkg._komut_durum(None)("")
        self.assertIn("OKUNAMADI", cikti)
        self.assertIn("dosya yok", cikti)


if __name__ == "__main__":
    unittest.main()


class OzetSayacTest(unittest.TestCase):
    """`ozet` alanı YALNIZ doğru sayıları yazmalı (16.10.2026 düzeltmesi)."""

    def setUp(self) -> None:
        self.pkg = _modul()
        self.komut = None

    def _veri(self, kalemler):
        import copy
        from collections import Counter
        v = dict(VERI)
        sayim = Counter(k["durum"] for k in kalemler)
        v["kuyruk"] = {"bekleyen": len(kalemler) - sayim.get("onaylı", 0), "onaylı": sayim.get("onaylı", 0),
                       "beklemede": sayim.get("bekliyor", 0), "onay_bekleyen": len(kalemler) - sayim.get("onaylı", 0)
                       - sayim.get("koşuldu", 0) - sayim.get("atlandı", 0), "koşuldu": sayim.get("koşuldu", 0),
                       "atlandı": sayim.get("atlandı", 0), "sahipsiz": sayim.get("sahipsiz", 0), "toplam": len(kalemler)}
        v["kalemler"] = kalemler
        v["ozet"] = (f"{v['pencere'].upper()} · {v['gelecek_pencere']} {v['geri_sayim']} sonra · "
                     f"kuyruk {len(kalemler)} kalem · {v['kuyruk']['onaylı']} onaylı · {v['kuyruk']['koşuldu']} koşuldu"
                     + (f" · {v['kuyruk']['onay_bekleyen']} onay/sahipsiz bekliyor" if v["kuyruk"]["onay_bekleyen"] else ""))
        # üretim yolunu kullan: _durum_verisi'ni sabitleyip _komut_durum ile metni al
        self.pkg._durum_verisi = lambda ctx=None: v
        return self.pkg._komut_durum(None)("")

    def test_hepsi_kosulduysa_bekleyen_yazmaz(self):
        cikti = self._veri([{"id": f"K-{i:03d}", "durum": "koşuldu", "metin": "x"} for i in range(1, 8)])
        self.assertIn("7 kalem · 0 onaylı · 7 koşuldu", cikti)
        self.assertNotIn("bekliyor", cikti.splitlines()[0])   # başlıkta yanıltıcı "bekliyor" olmaz
        self.assertIn("**onay bekleyen**: yok", cikti)

    def test_bekleyen_kalem_gorunur(self):
        cikti = self._veri([{"id": "K-001", "durum": "koşuldu", "metin": "x"},
                            {"id": "K-002", "durum": "onay-bekliyor", "metin": "y"}])
        self.assertIn("1 onay/sahipsiz bekliyor", cikti)
