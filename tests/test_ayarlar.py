"""Ayar katmanı testleri: ``plugin.yaml`` ↔ ``bekci_core`` ↔ masaüstü çekirdeği.

Varlık nedeni: ayarların TEK beyan kaynağı ``plugin.yaml`` → ``config_schema``'dır; kod
varsayılanları oradan okur (``bekci_core.VARSAYILAN_AYARLAR``). Beyan ile okunan ayrışırsa
burada yakalanır — böylece "yeni ayar eklerken tek yeri düzelt" kuralı kanıtlanır.

Ayrıca iki sınıf hatayı da yakalar:
  * kullanıcıya özel sabit yol/değer (ör. kişisel çalışma alanı) eklentiye gömülmesi,
  * py ile masaüstü JS yarısının ortak ayar ADLARINDAN ayrışması (JS py'yi import edemez).

Çalıştırma: `python3 -m unittest discover -s tests -t . -v`
"""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bekci_core as c  # noqa: E402

KOK = Path(__file__).resolve().parents[1]
PLUGIN_YAML = KOK / "plugin.yaml"
CEKIRDEK_JS = KOK / "desktop" / "bekci-cekirdek.js"
KABUK_JS = KOK / "desktop" / "kabuk.js"
PLUGIN_JS = KOK / "desktop" / "plugin.js"
KATALOG = KOK / "plugin-catalog" / "offpeak-bekci.yaml"

#: Kullanıcıya özel hiçbir yolda geçmemesi gereken imler (eklenti genel bir araçtır).
KISISEL_IMLER = ("MacAir", "/Users/")

#: hermes-agent manifest doğrulayıcısının kabul ettiği tip adları (bilinen küme).
BILINEN_TIPLER = {
    "str", "string", "int", "integer", "float", "number", "bool", "boolean",
    "list", "array", "dict", "object", "secret",
}


def _sema() -> dict:
    """``plugin.yaml`` → ``config_schema`` (yaml ile; dosya bozuksa testler patlar, bu doğru)."""
    import yaml

    return yaml.safe_load(PLUGIN_YAML.read_text(encoding="utf-8"))["config_schema"]


def _js_ortak_anahtarlar() -> list:
    """``desktop/bekci-cekirdek.js`` içindeki ``ORTAK_AYAR_ANAHTARLARI`` listesi."""
    metin = CEKIRDEK_JS.read_text(encoding="utf-8")
    blok = re.search(r"ORTAK_AYAR_ANAHTARLARI\s*=\s*\[(.*?)\]", metin, re.S)
    if not blok:
        raise AssertionError("cekirdek.js: ORTAK_AYAR_ANAHTARLARI bulunamadı")
    return re.findall(r"'([^']+)'", blok.group(1))


class SemaTest(unittest.TestCase):
    def test_manifest_v2_ve_isim(self):
        import yaml

        veri = yaml.safe_load(PLUGIN_YAML.read_text(encoding="utf-8"))
        self.assertEqual(veri["name"], "offpeak-bekci")
        self.assertEqual(veri["manifest_version"], 2)  # config_schema'yı taşıyan sürüm

    def test_sema_tipleri_bilinen(self):
        for anahtar, spec in _sema().items():
            self.assertIn("type", spec, f"{anahtar}: `type` yok")
            self.assertIn(str(spec["type"]).lower(), BILINEN_TIPLER, f"{anahtar}: bilinmeyen tip")
            self.assertIn("default", spec, f"{anahtar}: `default` yok")
            self.assertTrue(str(spec.get("description", "")).strip(), f"{anahtar}: açıklama yok")

    def test_varsayilanlar_semadan_okunur(self):
        """``VARSAYILAN_AYARLAR`` = ``plugin.yaml`` varsayılanları (tek doğruluk kaynağı)."""
        sema = _sema()
        beklenen = {k: v["default"] for k, v in sema.items()}
        self.assertEqual(c.VARSAYILAN_AYARLAR, beklenen)

    def test_ayar_sirasi_ile_yedek_kapak_uyumlu(self):
        """Her sıralı anahtarın gömülü yedeği olmalı (yoksa şema okunamayan ortamda KeyError)."""
        self.assertEqual(set(c._AYAR_SIRASI), set(c._SEMA_YEDEGI))
        self.assertEqual(set(c._AYAR_SIRASI), set(c.VARSAYILAN_AYARLAR))
        self.assertEqual(len(c._AYAR_SIRASI), len(set(c._AYAR_SIRASI)))

    def test_sema_okunamazsa_gomulu_yedege_duser(self):
        self.assertEqual(c._plugin_semasi(str(KOK / "yok-boyle-dosya.yaml")), {})
        self.assertEqual(c._sema_varsayilanlari(sema={}), c._SEMA_YEDEGI)
        # bozuk/eksik default → o anahtar için yedeğe düşer, diğerleri şemadan gelir
        karisik = c._sema_varsayilanlari(sema={"hedef_hiz_dk": {"type": "int"}, "ileride": {"type": "int", "default": 7}})
        self.assertEqual(karisik["hedef_hiz_dk"], c._SEMA_YEDEGI["hedef_hiz_dk"])
        self.assertEqual(karisik["ileride"], 7)  # şemaya sonradan eklenen anahtar görünür olur

    def test_plugin_yaml_ve_masaustu_kisisel_yol_tasimaz(self):
        for yol in (PLUGIN_YAML, CEKIRDEK_JS, KABUK_JS, KATALOG):
            metin = yol.read_text(encoding="utf-8")
            for im in KISISEL_IMLER:
                self.assertNotIn(im, metin, f"{yol.name}: kullanıcıya özel sabit yol ({im})")
        # kuyruk dosyası artık genel bir yola işaret eder
        self.assertTrue(c.VARSAYILAN_AYARLAR["kuyruk_dosyasi"].startswith("~/.hermes/"))


class AyarlariBirlestirTest(unittest.TestCase):
    def test_kanonik_ad_takma_addan_ustun(self):
        a = c.ayarlari_birlestir({"t30_dk": "15", "bilinmeyen": 1})
        self.assertEqual(a["on_bildirim_dk"], 15)  # eski ad kanonik ada çevrildi
        self.assertNotIn("t30_dk", a)
        self.assertNotIn("bilinmeyen", a)

    def test_takma_ad_yalniz_yoksa_kullanilir(self):
        a = c.ayarlari_birlestir({"t30_dk": 5, "on_bildirim_dk": 12})
        self.assertEqual(a["on_bildirim_dk"], 12)

    def test_tipleri_zorlar(self):
        a = c.ayarlari_birlestir({"kuru_kosu": "false", "hedef_hiz_dk": "9", "pencere_sn": "90"})
        self.assertIs(a["kuru_kosu"], False)
        self.assertEqual(a["hedef_hiz_dk"], 9)
        self.assertEqual(a["pencere_sn"], 90.0)
        self.assertIsInstance(a["pencere_sn"], float)

    def test_bos_deger_varsayilani_ezmez(self):
        a = c.ayarlari_birlestir({"hedef_hiz_dk": None, "kota_tavani": None})
        self.assertEqual(a, c.VARSAYILAN_AYARLAR)

    def test_liste_ayari_kopyalanir_ve_metinden_bolunur(self):
        kaynak = ["rapor", "envanter"]
        a = c.ayarlari_birlestir({"off_peak_only_isler": kaynak})
        self.assertEqual(a["off_peak_only_isler"], kaynak)
        a["off_peak_only_isler"].append("x")
        self.assertEqual(kaynak, ["rapor", "envanter"], "çağıranın listesi paylaşılmamalı")
        self.assertEqual(c.ayarlari_birlestir({"off_peak_only_isler": "a, b"})["off_peak_only_isler"], ["a", "b"])

    def test_sozluk_olmayan_girdi_varsayilan_dondurur(self):
        for ham in (None, [], "x", 3, True):
            self.assertEqual(c.ayarlari_birlestir(ham), c.VARSAYILAN_AYARLAR)

    def test_etkin_ayarlar_sekil_ve_varsayilanlar(self):
        veri = c.etkin_ayarlar(c.ayarlari_birlestir({"hedef_hiz_dk": 15}))
        self.assertEqual(veri["hedef_hiz_dk"], 15)
        self.assertEqual(veri["varsayilanlar"], c.VARSAYILAN_AYARLAR)
        self.assertIn("schedule_gecerli", veri)
        for anahtar in c.VARSAYILAN_AYARLAR:
            self.assertIn(anahtar, veri)
        # sır yok: yalnız beyan edilen anahtarlar + iki türev alan
        self.assertEqual(set(veri) - set(c.VARSAYILAN_AYARLAR), {"schedule_gecerli", "varsayilanlar"})
        json.dumps(veri)  # JSON'a serileşebilmeli (masaüstü bu alanı okur)

    def test_schedule_dogrulama(self):
        self.assertTrue(c.schedule_gecerli_mi("5 18 * * 1-5"))
        self.assertTrue(c.schedule_gecerli_mi("* * * * *"))
        self.assertFalse(c.schedule_gecerli_mi("18:05"))
        self.assertFalse(c.schedule_gecerli_mi("5 18 * *"))  # 4 alan
        self.assertFalse(c.schedule_gecerli_mi(""))
        self.assertFalse(c.schedule_gecerli_mi(None))
        self.assertFalse(c.schedule_gecerli_mi("5 18 * * 1-5; rm -rf /"))  # ifade değil, kabuk yok
        # beyan edilen varsayılan geçerli olmalı
        self.assertTrue(c.schedule_gecerli_mi(c.VARSAYILAN_AYARLAR["schedule"]))


class MasaustuUyumTest(unittest.TestCase):
    def test_js_ayar_tipleri_plugin_yaml_ile_ayni(self):
        """Masaüstü tip haritası ``plugin.yaml`` tiplerinden türemeli (yoksa zorlama ayrışır)."""
        metin = CEKIRDEK_JS.read_text(encoding="utf-8")
        blok = re.search(r"AYAR_TIPLERI\s*=\s*\{(.*?)\n\}", metin, re.S)
        self.assertIsNotNone(blok, "cekirdek.js: AYAR_TIPLERI bulunamadı")
        js = dict(re.findall(r"(\w+):\s*'(\w+)'", blok.group(1)))
        beklenen = {}
        for anahtar, spec in _sema().items():
            tip = str(spec["type"]).lower()
            beklenen[anahtar] = {
                "bool": "mantik", "boolean": "mantik",
                "list": "liste", "array": "liste",
                "int": "tam", "integer": "tam",
                "float": "ondalik", "number": "ondalik",
            }.get(tip, "metin")
        self.assertEqual(js, beklenen)

    def test_tip_zorlamasi_py_ile_ayni_ornekler(self):
        """Aynı girdiler iki yarıda aynı sonucu vermeli (JS testinde aynı örnekler ölçülür)."""
        a = c.ayarlari_birlestir({"hedef_hiz_dk": "9", "kuru_kosu": "false", "pencere_sn": "90"})
        self.assertEqual(a["hedef_hiz_dk"], 9)
        self.assertIs(a["kuru_kosu"], False)
        self.assertEqual(a["pencere_sn"], 90.0)
        self.assertEqual(c.ayarlari_birlestir({"on_bildirim_dk": "x"})["on_bildirim_dk"], 30)  # çevrilemez → varsayılan
        self.assertEqual(c.ayarlari_birlestir({"on_bildirim_dk": ""})["on_bildirim_dk"], 30)

    def test_js_ve_py_ortak_ayar_adlari_ayni(self):
        """İki yarım aynı ayar adlarını bilmeli (JS py'yi import edemez → test kapıdır)."""
        self.assertEqual(sorted(_js_ortak_anahtarlar()), sorted(c.VARSAYILAN_AYARLAR))

    def test_gomulu_plugin_js_bayat_degil(self):
        """``desktop/plugin.js`` ayar işini içermeli (node derleyicisi bayat bıraktıysa yakala)."""
        metin = PLUGIN_JS.read_text(encoding="utf-8")
        self.assertIn("export function ayarlariBirlestir(", metin)
        self.assertIn("ORTAK_AYAR_ANAHTARLARI", metin)
        for im in KISISEL_IMLER:
            self.assertNotIn(im, metin, f"plugin.js: kullanıcıya özel sabit yol ({im})")
        # gömülü çekirdek bayat olmamalı: çekirdeğin ayar bloğu üretilen dosyada birebir durur
        cekirdek = CEKIRDEK_JS.read_text(encoding="utf-8")
        self.assertIn(cekirdek[cekirdek.index("export const VARSAYILAN_AYAR"):cekirdek.index("const GUN_MS")], metin)

    def test_kabuk_backend_ayarlarini_okur(self):
        """Masaüstü yarısı backend'in etkin ayarlarını (``ayar`` alanı) birleştirmeli."""
        metin = KABUK_JS.read_text(encoding="utf-8")
        self.assertIn("ayarCoz(yanit)", metin)
        self.assertIn("ayarlariBirlestir(", metin)


if __name__ == "__main__":
    unittest.main()
