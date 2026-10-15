"""``bekci_core`` sınır/karar testleri (yalnız stdlib — pytest GEREKMEZ).

Çalıştırma: `python3 -m unittest discover -s tests -t . -v`
"""
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bekci_core as c  # noqa: E402

PZT = "2026-10-19T"


def an(iso):
    return c._dt.datetime.fromisoformat(iso)


class PeakPencereTest(unittest.TestCase):
    def test_peak_sinirlari(self):
        for iso, beklenen in [
            (f"{PZT}11:59:59+00:00", False),
            (f"{PZT}12:00:00+00:00", True),
            (f"{PZT}17:59:59+00:00", True),
            (f"{PZT}18:00:00+00:00", False),
            ("2026-10-23T17:59:59+00:00", True),
            ("2026-10-23T18:00:00+00:00", False),
            ("2026-10-24T12:00:00+00:00", False),
            ("2026-10-25T12:00:00+00:00", False),
        ]:
            with self.subTest(iso=iso):
                self.assertIs(c.peak_mi(an(iso)), beklenen)

    def test_pencere_adi(self):
        self.assertEqual(c.pencere(an(f"{PZT}12:00:00+00:00")), "peak")
        self.assertEqual(c.pencere(an(f"{PZT}18:00:00+00:00")), "off-peak")

    def test_sonraki_gecis_ileri_gider(self):
        self.assertEqual(c.sonraki_gecis(an(f"{PZT}17:30:00+00:00"))[1], an(f"{PZT}18:00:00+00:00"))
        self.assertEqual(c.sonraki_gecis(an(f"{PZT}18:00:00+00:00"))[1], an("2026-10-20T12:00:00+00:00"))
        self.assertEqual(c.sonraki_gecis(an("2026-10-23T18:30:00+00:00"))[1], an("2026-10-26T12:00:00+00:00"))
        self.assertEqual(c.sonraki_gecis(an("2026-10-24T00:00:00+00:00"))[1], an("2026-10-26T12:00:00+00:00"))

    def test_kalan_ve_geri_sayim(self):
        self.assertEqual(c.kalan_saniye(an(f"{PZT}17:30:00+00:00")), 1800)
        self.assertEqual(c.geri_sayim(an(f"{PZT}17:30:00+00:00")), "00:30")
        self.assertEqual(c.geri_sayim(an(f"{PZT}17:29:59+00:00")), "00:31")
        self.assertEqual(c.kalan_saniye(an("2026-10-24T00:00:00+00:00")), 216000)
        self.assertEqual(c.geri_sayim(an("2026-10-24T00:00:00+00:00")), "60:00")

    def test_offpeak_anahtari_hafta_sonu_tek_blok(self):
        cuma = an("2026-10-23T18:00:00+00:00").isoformat()
        self.assertEqual(c.offpeak_anahtari(an("2026-10-24T10:00:00+00:00")), cuma)
        self.assertEqual(c.offpeak_anahtari(an("2026-10-25T20:00:00+00:00")), cuma)
        self.assertNotEqual(c.offpeak_anahtari(an("2026-10-26T18:00:00+00:00")), cuma)

    def test_t30_hatirlatmasi(self):
        self.assertIs(c.offpeak_hatirlatma_mi(an(f"{PZT}17:00:00+00:00")), False)
        self.assertIs(c.offpeak_hatirlatma_mi(an(f"{PZT}17:30:00+00:00")), True)
        self.assertIs(c.offpeak_hatirlatma_mi(an(f"{PZT}19:00:00+00:00")), False)
        self.assertIs(c.offpeak_hatirlatma_mi(an("2026-10-24T17:30:00+00:00")), False)

    def test_ozet_anahtarlari(self):
        o = c.ozet(an(f"{PZT}17:45:00+00:00"))
        for k in ("pencere", "peak_mi", "gelecek_pencere", "gelecek_gecis_utc",
                  "kalan_sn", "geri_sayim", "t30_dk", "t30_icerisinde", "offpeak_anahtari"):
            self.assertIn(k, o)
        self.assertEqual((o["pencere"], o["kalan_sn"], o["geri_sayim"]), ("peak", 900, "00:15"))
        self.assertIs(o["t30_icerisinde"], True)
        json.dumps(o, ensure_ascii=False)


class PolitikaTest(unittest.TestCase):
    def test_gecikme_peak_ve_offpeak(self):
        pik = c.gecikme_planla(an(f"{PZT}13:00:00+00:00"), 8, kuru_kosu=False)
        self.assertEqual((pik["fazla"], pik["gerekli_sn"], pik["uygulanacak_sn"]), (2, 20.0, 20.0))
        off = c.gecikme_planla(an(f"{PZT}19:00:00+00:00"), 30, kuru_kosu=False)
        self.assertEqual((off["gerekli_sn"], off["uygulanacak_sn"]), (0.0, 0.0))

    def test_gecikme_tavani_ve_kuru_kosu(self):
        tav = c.gecikme_planla(an(f"{PZT}13:00:00+00:00"), 60, erteleme_tavani_sn=30.0, kuru_kosu=False)
        self.assertEqual((tav["gerekli_sn"], tav["uygulanacak_sn"]), (480.0, 30.0))
        kuru = c.gecikme_planla(an(f"{PZT}13:00:00+00:00"), 60, kuru_kosu=True)
        self.assertEqual((kuru["gerekli_sn"], kuru["uygulanacak_sn"]), (480.0, 0.0))

    def test_kayan_pencere(self):
        p = c.KayanPencere(60.0)
        self.assertEqual(p.kayit(1000.0), 1)
        self.assertEqual(p.kayit(1030.0), 2)
        self.assertEqual(p.sayi(1070.0), 2)
        self.assertEqual(p.kayit(1070.0), 1)
        p.sifirla()
        self.assertEqual(p.sayi(1070.0), 0)

    def test_kota_durumu(self):
        self.assertEqual(c.kota_durumu(3, 5), {"sayi": 3, "tavan": 5, "asildi": False, "uyari": False})
        self.assertEqual(c.kota_durumu(5, 5), {"sayi": 5, "tavan": 5, "asildi": True, "uyari": True})
        self.assertEqual(c.kota_durumu(9, 5)["uyari"], False)

    def test_ollama_bulut_mu(self):
        self.assertIs(c.ollama_bulut_mu(base_url="https://ollama.com"), True)
        self.assertIs(c.ollama_bulut_mu(model="gpt-oss:120b-cloud"), True)
        self.assertIs(c.ollama_bulut_mu(provider="ollama-cloud"), True)
        self.assertIs(c.ollama_bulut_mu(base_url="http://192.168.1.9:11434"), False)
        self.assertIs(c.ollama_bulut_mu(base_url="http://127.0.0.1:11434"), False)

    def test_ayarlari_birlestir_ve_yol(self):
        a = c.ayarlari_birlestir({"t30_dk": "15", "bilinmeyen": 1})
        self.assertEqual(a["t30_dk"], 15)
        self.assertNotIn("bilinmeyen", a)
        self.assertEqual(c.ayarlari_birlestir(None), c.VARSAYILAN_AYARLAR)
        self.assertTrue(c.yol_genislet("~/x").startswith(os.path.expanduser("~")))


TABLO = """\
| id | iş | sahip | kanıt ölçütü | durum | pencere |
|----|----|-------|--------------|-------|---------|
| K-001 | **Bağlam** | MacAir / default | rapor | onay-bekliyor | Cuma 21:00 |
| K-002 | **Skill envanteri** | MacAir / default | rapor | onaylı | Cuma 21:00 |
| 2026-10-09 | 1.086 | 7.183.437 | 292.606.192 |  |  |
| — | — | — | — | — | — |
- id: K-003 · durum: onay-bekliyor · efor: e-2
- **Salt gövde metni kalem sayılmaz.**
- [ ] K-004 kutulu satır
Düz metin.
"""


class KuyrukTest(unittest.TestCase):
    def test_ayristirma(self):
        kalemler = c.kuyruk_ayristir(TABLO)
        self.assertEqual([k["id"] for k in kalemler], ["K-001", "K-002", "K-003", "K-004"])
        self.assertEqual([k["durum"] for k in kalemler], ["bekliyor", "onaylı", "bekliyor", "bekliyor"])
        self.assertEqual(kalemler[2]["efor"], "e-2")

    def test_sayilar(self):
        s = c.kuyruk_sayilari(c.kuyruk_ayristir(TABLO))
        self.assertEqual((s["toplam"], s["onaylı"], s["bekleyen"], s["beklemede"]), (4, 1, 3, 3))

    def test_onayla_bayt_korur_ve_tekil(self):
        yeni, degisen = c.kuyruk_onayla(TABLO, ["K-001"])
        self.assertEqual(degisen, ["K-001"])
        eski, y = TABLO.splitlines(), yeni.splitlines()
        self.assertEqual(len(eski), len(y))
        fark = [i for i, (a, b) in enumerate(zip(eski, y)) if a != b]
        self.assertEqual(fark, [2])
        self.assertIn("onaylı", y[2])
        self.assertNotIn("onay-bekliyor", y[2])
        self.assertEqual(y[3], eski[3])
        tekrar, degisen2 = c.kuyruk_onayla(yeni, ["K-001"])
        self.assertEqual(degisen2, [])
        self.assertEqual(tekrar, yeni)
        self.assertEqual([k["id"] for k in c.kuyruk_ayristir(yeni)], ["K-001", "K-002", "K-003", "K-004"])

    def test_madde_bicimi_onaylama(self):
        metin = "- id: K-9 · durum: onay-bekliyor\n- [ ] K-10 iş\n"
        yeni, degisen = c.kuyruk_onayla(metin, ["K-9", "K-10"])
        self.assertEqual(degisen, ["K-9", "K-10"])
        self.assertIn("durum: onaylı", yeni)
        self.assertTrue(yeni.splitlines()[1].startswith("- [x] K-10"))

    def test_id_listesi_coz(self):
        self.assertEqual(c.id_listesi_coz("K-001, K-002 K-002   T-9"), ["K-001", "K-002", "T-9"])
        self.assertEqual(c.id_listesi_coz(""), [])


GERCEK = Path.home() / "MacAir" / "off-peak-kuyruk.md"


class GercekDosyaTest(unittest.TestCase):
    @unittest.skipUnless(GERCEK.exists(), "kullanıcının kuyruk dosyası yok")
    def test_gercek_kuyruk_dosyasi(self):
        kalemler = c.kuyruk_ayristir(GERCEK.read_text(encoding="utf-8"))
        kimlikler = [k["id"] for k in kalemler]
        self.assertTrue(kimlikler)
        self.assertIn("K-001", kimlikler)
        for k in kalemler:
            self.assertIn(k["durum"], {"bekliyor", "onaylı", "koşuldu", "atlandı", "sahipsiz"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
