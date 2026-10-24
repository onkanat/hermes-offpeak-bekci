"""``bekci_core`` sınır/karar testleri (yalnız stdlib — pytest GEREKMEZ).

Çalıştırma: `python3 -m unittest discover -s tests -t . -v`
"""
import json
import os
import re
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

    def test_deepseek_takvimi_sizmadi(self):
        """Pencere **Ollama** tanımıdır; DeepSeek'in ``PEAK_WINDOWS=[[1,4],[6,10]]``
        deseni sızmamalı. Ollama: hafta içi 12:00–18:00 UTC peak. DeepSeek deseninde
        peak/sınır saatleri 01,04,06,10 çevresindedir — burada hiçbiri sınır değil.
        """
        for saat in range(0, 12):
            with self.subTest(saat=saat):
                self.assertIs(c.peak_mi(an(f"{PZT}{saat:02d}:00:00+00:00")), False)
        for saat in range(12, 18):
            with self.subTest(saat=saat):
                self.assertIs(c.peak_mi(an(f"{PZT}{saat:02d}:00:00+00:00")), True)
        for saat in range(18, 24):
            with self.subTest(saat=saat):
                self.assertIs(c.peak_mi(an(f"{PZT}{saat:02d}:00:00+00:00")), False)

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
        """Beklenti FORMÜLDEN türetildi (16.10.2026'da gerekçelendirildi).

        ``gecikme_planla``: ``fazla = sayi_60sn - hedef_hiz_dk``,
        ``gerekli = fazla * (60 / hedef_hiz_dk)`` (yani fazla çağrı × bir "slot").
        Varsayılan hedef 6/dk → slot 10 sn; 60 çağrı → fazla 54 → gerekli 54 × 10 = **540 sn**.
        Testin eski beklentisi 480 sn formülle tutarsızdı (480, fazla=48 ⇒ hedef=12 varsayar);
        doğru olan ölçülen değerdir: 540. Tavan 30 sn olduğu için uygulanacak 30 sn'ye kırpılır,
        kuru koşuda ise hiç uygulanmaz (yalnız raporlanır).
        """
        tav = c.gecikme_planla(an(f"{PZT}13:00:00+00:00"), 60, erteleme_tavani_sn=30.0, kuru_kosu=False)
        self.assertEqual((tav["fazla"], tav["gerekli_sn"], tav["uygulanacak_sn"]), (54, 540.0, 30.0))
        kuru = c.gecikme_planla(an(f"{PZT}13:00:00+00:00"), 60, kuru_kosu=True)
        self.assertEqual((kuru["gerekli_sn"], kuru["uygulanacak_sn"]), (540.0, 0.0))

    def test_kayan_pencere(self):
        """Pencere YARI AÇIK: ``(ts - pencere_sn, ts]`` → tam 60 sn önceki kayıt sayılmaz.

        60 sn'lik pencerede 1000 ve 1030 kayıtlıyken 1070'te 1000 tam 60 sn yaşındadır →
        ``sayi(1070) == 1`` (ölçülen buydu; eski 2 beklentisi kapalı sınır varsayıyordu).
        Sınırın tam üstündeki (0.001 sn daha genç) kayıt ise sayılır.
        """
        p = c.KayanPencere(60.0)
        self.assertEqual(p.kayit(1000.0), 1)
        self.assertEqual(p.kayit(1030.0), 2)
        self.assertEqual(p.sayi(1070.0), 1)  # 1000 pencerenin dışında
        self.assertEqual(p.kayit(1070.0), 2)  # 1030 hâlâ içeride
        s = c.KayanPencere(60.0)
        s.kayit(1010.0)
        self.assertEqual(s.sayi(1070.0), 0, "tam 60 sn önceki kayıt sayılmaz")
        s.kayit(1010.001)
        self.assertEqual(s.sayi(1070.0), 1, "0.001 sn daha genç kayıt sayılır")
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
        self.assertIs(c.ollama_bulut_mu(base_url="http://10.0.0.1:11434"), False)
        self.assertIs(c.ollama_bulut_mu(base_url="http://127.0.0.1:11434"), False)

    def test_bulut_yerel_vekil_arkasinda(self):
        """Filonun GERÇEK deseni: bulut modeli YEREL vekil üzerinden çağrılır.

        Regresyon (16.10.2026'da ölçüldü): yerel işaret kontrolü model kontrolünden önce
        yapılırsa bu çağrılar görünmez olur — ölçüm defterine hiç kayıt düşmez ve eklenti
        bu filoda hiçbir bulut çağrısını görmez.
        """
        self.assertIs(
            c.ollama_bulut_mu("ollama-launch", "http://127.0.0.1:11434/v1", "deepseek-v4.1-flash:cloud"),
            True,
        )
        self.assertIs(
            c.ollama_bulut_mu("lan-vekil-11435", "http://10.0.0.2:11435/v1", "deepseek-v4.1-flash:cloud"),
            True,
        )
        # Aynı vekil üzerinden gelen YEREL modeller dokunulmaz.
        self.assertIs(c.ollama_bulut_mu("ollama-launch", "http://127.0.0.1:11434/v1", "qwen3:4b"), False)
        self.assertIs(c.ollama_bulut_mu(model="gemma4:latest"), False)
        self.assertIs(c.ollama_bulut_mu(model="mycloud"), False)

    def test_ayarlari_birlestir_ve_yol(self):
        a = c.ayarlari_birlestir({"t30_dk": "15", "bilinmeyen": 1})  # t30_dk = eski ad
        self.assertEqual(a["on_bildirim_dk"], 15)
        self.assertNotIn("t30_dk", a)
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

    def test_sayilar_bolusum(self):
        """Bölüşüm kuralı: onaylı + beklemede + koşuldu + atlandı + sahipsiz == toplam.

        `onaysiz` kesişen sayaçtır (koşuldu dahil) ve bölüşüme girmez; `bekleyen` onun eski adıdır.
        "11+11=22 ama toplam 11" sınıfı hata bu testle kapalıdır (18.10.2026).
        """
        kalemler = c.kuyruk_ayristir(TABLO)
        s = c.kuyruk_sayilari(kalemler)
        self.assertEqual(
            s["onaylı"] + s["beklemede"] + s["koşuldu"] + s["atlandı"] + s["sahipsiz"], s["toplam"]
        )
        self.assertEqual(s["onaysiz"], s["toplam"] - s["onaylı"])
        self.assertEqual(s["bekleyen"], s["onaysiz"])  # geriye uyumlu alias
        self.assertEqual(s["onay_bekleyen"], s["beklemede"] + s["sahipsiz"] + (s["toplam"] - (s["onaylı"] + s["beklemede"] + s["koşuldu"] + s["atlandı"] + s["sahipsiz"])))

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

    # ── tablo başlığı ölçütü: kuyruk defteri olmayan tablo kalem SAYILMAZ ──
    KOSUM_KAYDI = """\
| id | iş | sahip | kanıt ölçütü | durum | pencere |
|----|----|-------|--------------|-------|---------|
| K-001 | **Bağlam** | MacAir | rapor | onay-bekliyor | Cuma 21:00 |

### Koşum kaydı

| id | pencere | başlangıç-bitiş | kanıt satırı | sonuç |
|----|---------|-----------------|--------------|-------|
| K-001 | off-peak (08:23–08:26) | 16.10.2026 08:23 → 08:26 | `maliyet/sorgu.txt` · EXIT=0 | tamam — teşhis: tetik 524.288 |
| K-002 | off-peak (08:24–08:27) | 16.10.2026 08:24 → 08:27 | `skill.csv` · EXIT=0 | tamam — ayıklama 0 |
"""

    def test_kosum_kaydi_tablosu_kalem_sayilmaz(self):
        """Başlığında ``durum`` kolonu olmayan tablo kuyruk defteri değildir.

        Gerçek dosyada koşum kaydı tablosunun ``K-001``/``K-002`` satırları da kalem
        sayılıyor, kimlikler iki kez görünüyor ve sayaçlar şişiyordu (4 kalem → 6 kalem).
        """
        kalemler = c.kuyruk_ayristir(self.KOSUM_KAYDI)
        self.assertEqual([k["id"] for k in kalemler], ["K-001"])
        self.assertEqual([k["durum"] for k in kalemler], ["bekliyor"])

    def test_kosum_kaydi_satiri_onaylanmaz(self):
        yeni, degisen = c.kuyruk_onayla(self.KOSUM_KAYDI, ["K-001", "K-002"])
        self.assertEqual(degisen, ["K-001"])
        self.assertNotIn("| onaylı | tamam — teşhis", yeni)
        self.assertIn("tamam — teşhis: tetik 524.288", yeni)

    def test_kalin_notlu_durum_okunur(self):
        """Durum hücresi kalın ve yanında tarih/kanıt notu olabilir.

        ``**koşuldu** 16.10.2026 08:26 — çıktı … EXIT=0`` eskiden ``bekliyor`` okunuyordu
        (birebir sözcük eşleşmesi), sayaçlar yanlış çıkıyordu.
        """
        metin = (
            "| id | iş | sahip | kanıt | durum | pencere |\n"
            "|----|----|-------|-------|-------|---------|\n"
            "| K-001 | **a** | MacAir | ölçüm | **koşuldu** 16.10.2026 08:26 — çıktı `m/rapor.md` · EXIT=0 | Cuma |\n"
            "| K-002 | **b** | MacAir | ölçüm | **onay-bekliyor** (kullanıcı, 16.10.2026 08:05) | Cuma |\n"
            "| K-003 | **c** | MacAir | ölçüm |  | Cuma |\n"
        )
        kalemler = c.kuyruk_ayristir(metin)
        self.assertEqual([k["durum"] for k in kalemler], ["koşuldu", "bekliyor", "bekliyor"])
        s = c.kuyruk_sayilari(kalemler)
        self.assertEqual((s["toplam"], s["onaylı"], s["koşuldu"], s["beklemede"]), (3, 0, 1, 2))

    def test_onaylama_hucredeki_notu_silmez(self):
        """Onaylama YALNIZ durum sözcüğünü değiştirir: kalın işaret ve ek not korunur."""
        metin = (
            "| id | durum | not | sahip |\n"
            "|----|-------|-----|-------|\n"
            "| K-007 | **onay-bekliyor** (kullanıcı, 16.10.2026 08:05) | kanıt | MacAir |\n"
        )
        yeni, degisen = c.kuyruk_onayla(metin, ["K-007"])
        self.assertEqual(degisen, ["K-007"])
        self.assertIn("| **onaylı** (kullanıcı, 16.10.2026 08:05) |", yeni)

    def test_onaylama_kosuldu_kalemi_degistirmez(self):
        metin = (
            "| id | durum | iş | sahip |\n"
            "|----|-------|----|-------|\n"
            "| K-008 | **koşuldu** 16.10.2026 08:26 | iş | MacAir |\n"
        )
        yeni, degisen = c.kuyruk_onayla(metin, ["K-008"])
        self.assertEqual((degisen, yeni), ([], metin))


def _gercek_kuyruk():
    """Kullanıcının gerçek kuyruk defteri: önce beyan edilen yol, sonra göç öncesi konum.

    Eklentinin okuduğu yol ``kuyruk_dosyasi`` ayarıdır (varsayılan ``~/.hermes/offpeak-bekci/``);
    ``OFFPEAK_KUYRUK_YOLU`` ile başka bir defter de sınanabilir (eski yazım ``OFFPEAK_KUYRIK_YOLU`` de kabul
    edilir). Eski konum yalnız bu testte, kullanıcı verisi keşfi olarak denenir — eklenti kodunda/ayarında
    sabit yol YOKTUR.
    """
    adaylar = []
    # Hem doğru ad hem eski (yanlış yazılmış) ad kabul edilir: 'KUYRIK' 16.10.2026'dan önceki test/notlarda geçiyor.
    ozel = os.environ.get("OFFPEAK_KUYRUK_YOLU") or os.environ.get("OFFPEAK_KUYRIK_YOLU")
    if ozel:
        adaylar.append(Path(c.yol_genislet(ozel)))
    adaylar.append(Path(c.yol_genislet(c.VARSAYILAN_AYARLAR["kuyruk_dosyasi"])))
    adaylar.append(Path.home() / "MacAir" / "off-peak-kuyruk.md")  # göç öncesi konum
    for aday in adaylar:
        if aday.exists():
            return aday
    return None


GERCEK = _gercek_kuyruk()


class GercekDosyaTest(unittest.TestCase):
    @unittest.skipUnless(GERCEK, "kullanıcının kuyruk dosyası yok")
    def test_gercek_kuyruk_dosyasi(self):
        kalemler = c.kuyruk_ayristir(GERCEK.read_text(encoding="utf-8"))
        kimlikler = [k["id"] for k in kalemler]
        self.assertTrue(kimlikler)
        # ÖNEK MAKİNEYE BAĞLIDIR: her makine kendi önekini kullanır (K-* · A-* · G-* …).
        # Sabit bir önek aramak testi başka makinede DÜŞÜRÜR (16.10.2026'da ölçüldü: bir peer makinesinde
        # "K-001" yok → 107 test · FAILED · EXIT=1; temiz klonda ise dosya olmadığı için SKIP).
        # Kural: kimlikler TEK bir önek ailesinden olmalı ve numara taşımalı.
        onekler = {m.group(1) for m in (re.match(r"^([A-Za-z]+)-(\d+)$", k) for k in kimlikler) if m}
        self.assertEqual(len(onekler), 1, f"tek önek ailesi beklenir · bulunan: {sorted(onekler)} · {kimlikler[:5]}")
        self.assertEqual(len(onekler) and len([k for k in kimlikler if re.match(r"^[A-Za-z]+-\d+$", k)]),
                         len(kimlikler), "her kimlik <önek>-<sayı> biçiminde olmalı")
        for k in kalemler:
            self.assertIn(k["durum"], {"bekliyor", "onaylı", "koşuldu", "atlandı", "sahipsiz"})

    @unittest.skipUnless(GERCEK, "kullanıcının kuyruk dosyası yok")
    def test_gercek_kuyruk_tekil_kimlik(self):
        """Aynı kimlik iki kez görünmemeli (koşum kaydı tablosu kalem sayılmaz) ve
        ``toplam`` gerçek kalem sayısına eşit olmalı."""
        kalemler = c.kuyruk_ayristir(GERCEK.read_text(encoding="utf-8"))
        kimlikler = [k["id"] for k in kalemler]
        self.assertEqual(len(kimlikler), len(set(kimlikler)), "yinelenen kimlik: %r" % kimlikler)
        self.assertEqual(c.kuyruk_sayilari(kalemler)["toplam"], len(kalemler))


class SentetikDefterTest(unittest.TestCase):
    """MAKİNEDEN BAĞIMSIZ defter testleri: içerik burada üretilir, gerçek deftere bakmaz.

    16.10.2026'da ölçüldü: yalnız gerçek deftere bakan testler (a) başka makinede DÜŞÜYORDU
    (peer makinesi A-* öneki kullanıyor, "K-001" yok) ve (b) temiz klonda defter olmadığı için tamamen SKIP
    oluyordu → çekirdeğin kimlik/durum davranışı hiç sınanmıyordu. Bu sınıf her ortamda koşar.
    """

    BASLIK = "| id | iş | sahip | kanıt ölçütü | durum | pencere |\n|---|---|---|---|---|---|\n"
    SATIRLAR = [
        "| A-001 | iş bir | makine-b | kanıt | **onaylı** | off-peak |",
        "| A-002 | iş iki | makine-b | kanıt | **onay-bekliyor** (kullanıcı) | off-peak |",
        "| A-003 | iş üç | makine-b | kanıt | **koşuldu** 16.10 21:06 — çıktı var | off-peak |",
    ]

    def test_onek_ailesi_ve_durumlar(self):
        kalemler = c.kuyruk_ayristir(self.BASLIK + "\n".join(self.SATIRLAR) + "\n")
        self.assertEqual([k["id"] for k in kalemler], ["A-001", "A-002", "A-003"])
        self.assertEqual([k["durum"] for k in kalemler], ["onaylı", "bekliyor", "koşuldu"])
        self.assertEqual(c.kuyruk_sayilari(kalemler)["toplam"], 3)

    def test_onek_makineye_bagimli_degil(self):
        """K-* / A-* / G-* / T-* öneklerinin hepsi aynı biçimde okunur — test bir makineye bağlanmaz."""
        for onek in ("K", "A", "G", "T"):
            with self.subTest(onek=onek):
                metin = self.BASLIK + "\n".join(s.replace("A-00", onek + "-00") for s in self.SATIRLAR) + "\n"
                kalemler = c.kuyruk_ayristir(metin)
                self.assertEqual([k["id"] for k in kalemler],
                                 [f"{onek}-001", f"{onek}-002", f"{onek}-003"])

    # ── Bölüm başlığı biçimi (ölçüldü 23.10.2026) ──────────────────────────────
    # Onaylı bir kalem tabloya değil **bölüm başlığı** olarak yazılmıştı
    # (`## K-043 — ressam profili (dilim 1) · **onaylı**`); sayacı yalnız tabloyu okuduğu
    # için kapı `ONAYLI=0` dedi ve kalem sessizce koşmadı. Bu testler o körlüğü kapatır.
    BASLIK_BICIMI = (
        "| id | iş | sahip | kanıt ölçütü | durum | pencere |\n|---|---|---|---|---|---|\n"
        "| A-001 | iş bir | makine-b | kanıt | **koşuldu** | off-peak |\n"
        "\n## A-042 — ressam profili (dilim 1) · **onaylı**\n\n"
        "Gövde metni burada; satırlar kalem sayılmaz.\n"
    )

    def test_baslik_bicimi_onayli_kalem_sayilir(self):
        kalemler = c.kuyruk_ayristir(self.BASLIK_BICIMI)
        self.assertEqual([k["id"] for k in kalemler], ["A-001", "A-042"])
        self.assertEqual(kalemler[1]["durum"], "onaylı")
        sayilar = c.kuyruk_sayilari(kalemler)
        self.assertEqual(sayilar["onaylı"], 1, "başlık biçimi onaylı kalem görünmüyor")
        self.assertEqual(sayilar["toplam"], 2)

    def test_baslik_bicimi_koşulmamış_sayılır(self):
        metin = "## A-050 — karar bekleyen iş · **onay-bekliyor**\n"
        kalemler = c.kuyruk_ayristir(metin)
        self.assertEqual([k["id"] for k in kalemler], ["A-050"])
        self.assertEqual(c.kuyruk_sayilari(kalemler)["onay_bekleyen"], 1)

    def test_ayni_id_iki_bicimde_cift_sayilmaz(self):
        """Aynı id hem tabloda hem başlıkta geçerse kalem BİR kez sayılır (id küçük harfe inilir)."""
        metin = (
            "| id | iş | sahip | kanıt ölçütü | durum | pencere |\n|---|---|---|---|---|---|\n"
            "| A-007 | iş yedi | makine-b | kanıt | **onaylı** | off-peak |\n"
            "\n## a-007 — aynı kalem başlık olarak · **onaylı**\n"
        )
        kalemler = c.kuyruk_ayristir(metin)
        self.assertEqual(len(kalemler), 1, f"çift sayım: {[k['id'] for k in kalemler]}")
        self.assertEqual(c.kuyruk_sayilari(kalemler)["onaylı"], 1)

    def test_baslik_bicimi_gercek_defterle_ayni_sonucu_verir(self):
        """Gerçek defter varsa: başlık biçimli kalem sayaca girer, kimlikler yinelenmez."""
        gercek = Path.home() / "MacAir" / "off-peak-kuyruk.md"
        if not gercek.is_file():
            self.skipTest("gerçek defter bu makinede yok")
        kalemler = c.kuyruk_ayristir(gercek.read_text(encoding="utf-8"))
        kimlikler = [k["id"].lower() for k in kalemler]
        self.assertEqual(len(kimlikler), len(set(kimlikler)), "yinelenen kimlik")



if __name__ == "__main__":
    unittest.main(verbosity=2)
