"""Ayar okuma zinciri testi (Kanban t_f8f21632, teslim 2).

Neden ayrı dosya: ``test_ayarlar.py`` şema/beyan uyumunu (``plugin.yaml`` ↔ ``bekci_core`` ↔
masaüstü JS) sınar; burada ise **çalışan zincir** sınanır: ``__init__._ham_ayarlar`` hangi katmanı
hangi katmanın üstüne koyuyor? Beyan (``bekci_core.AYAR_KATMAN_SIRASI`` + ``plugin.yaml``) ile
davranış ayrışırsa burada yakalanır.

Etkin sıra (yüksekten düşüğe) — ``bekci_core.AYAR_KATMAN_SIRASI``, şartname W4a-1 md.2:
  1. ``config.yaml``     → ``offpeak-bekci:`` bloğu (kurulumun ONAYLI eşikleri; ctx'i ve varsayılanı ezer)
  2. ``ctx.config``      → ``plugins.entries.offpeak-bekci.settings.*`` (bloğun bildirmediği anahtarları doldurur)
  3. şema varsayılanı    → ``plugin.yaml`` → ``config_schema[*].default``

Test hermetiktir: canlı ``config.yaml`` okunmaz — ``hermes_cli.config.load_config_readonly``
sahte bir modülle değiştirilir; ``ctx`` yerine ``test_middleware.SahteBaglam`` benzeri sahte
nesne verilir. Gerçek kurulumda defter yolu ``config.yaml`` bloğundan gelir (W4a-1 göçü).

Çalıştırma: `python3 -m unittest discover -s tests -t . -v`
"""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "offpeak_bekci_zincir_test", KOK / "__init__.py", submodule_search_locations=[str(KOK)]
)
assert _spec is not None and _spec.loader is not None
mod = importlib.util.module_from_spec(_spec)
sys.modules["offpeak_bekci_zincir_test"] = mod
_spec.loader.exec_module(mod)

core = mod.core

#: Şema varsayılanları (``plugin.yaml``): blok/ctx yokken geçerli olan katman.
SEMA_HEDEF_HIZ = core.VARSAYILAN_AYARLAR["hedef_hiz_dk"]
SEMA_KUYRUK = core.VARSAYILAN_AYARLAR["kuyruk_dosyasi"]
BLOK_HEDEF_HIZ = 15  # bu makinede onaylı eşik (varsayılan 6'dan farklı olması testi anlamlı kılar)


class SahteCtx:
    """``PluginContext`` yerine geçen sahte: yalnız verilen anahtarları döndürür."""

    def __init__(self, **ayarlar):
        self.ayarlar = ayarlar

    def get_config(self, anahtar, varsayilan=None):
        return self.ayarlar.get(anahtar, varsayilan)


class _SahteHermesConfig:
    """``hermes_cli.config.load_config_readonly`` sahtesi (kurulum gerekmez)."""

    def __init__(self, blok):
        self._blok = blok
        self._yedek = {}

    def __enter__(self):
        for ad in ("hermes_cli", "hermes_cli.config"):
            self._yedek[ad] = sys.modules.get(ad)
        paket = types.ModuleType("hermes_cli")
        paket.__path__ = []  # paket gibi davran (alt modül sys.modules'ta bulunur)
        yaprak = types.ModuleType("hermes_cli.config")
        setattr(yaprak, "load_config_readonly",
                lambda: ({"offpeak-bekci": self._blok} if self._blok is not None else {}))
        sys.modules["hermes_cli"] = paket
        sys.modules["hermes_cli.config"] = yaprak
        return self

    def __exit__(self, *bos):
        for ad, eski in self._yedek.items():
            if eski is None:
                sys.modules.pop(ad, None)
            else:
                sys.modules[ad] = eski
        return False


class AyarZinciriTest(unittest.TestCase):
    def setUp(self):
        # TTL önbelleği testler arası taşınmasın.
        with mod._kilit:
            mod._ayar_onbellek["ts"] = 0.0
            mod._ayar_onbellek["ayar"] = dict(core.VARSAYILAN_AYARLAR)

    # ── 2. katman: config.yaml bloğu varsayılanı ezer ────────────────────────────
    def test_config_bloku_sema_varsayilanini_ezer(self):
        with _SahteHermesConfig({"hedef_hiz_dk": BLOK_HEDEF_HIZ}):
            ayar = core.ayarlari_birlestir(mod._ham_ayarlar(None))
        self.assertEqual(ayar["hedef_hiz_dk"], BLOK_HEDEF_HIZ)
        self.assertNotEqual(ayar["hedef_hiz_dk"], SEMA_HEDEF_HIZ)

    def test_config_bloku_defter_yolunu_bildirir(self):
        """W4a-1: defter varsayılan konumda değilse yol kurulum bloğundan gelir."""
        with _SahteHermesConfig({"kuyruk_dosyasi": "~/paylasilan/off-peak-kuyruk.md"}):
            ayar = core.ayarlari_birlestir(mod._ham_ayarlar(None))
        self.assertEqual(ayar["kuyruk_dosyasi"], "~/paylasilan/off-peak-kuyruk.md")
        self.assertEqual(str(mod._kuyruk_yolu(ayar)).replace(str(Path.home()), "~"),
                         "~/paylasilan/off-peak-kuyruk.md")

    # ── 3. katman: hiçbir katman yoksa şema varsayılanı ─────────────────────────
    def test_katmansiz_sema_varsayilani_gecerli(self):
        with _SahteHermesConfig(None):
            ayar = core.ayarlari_birlestir(mod._ham_ayarlar(None))
        self.assertEqual(ayar["hedef_hiz_dk"], SEMA_HEDEF_HIZ)
        self.assertEqual(ayar["kuyruk_dosyasi"], SEMA_KUYRUK)

    # ── 1. katman: config.yaml bloğu ctx.config'i ezer (şartname W4a-1 md.2) ────
    def test_config_bloku_ctx_configi_ezer(self):
        with _SahteHermesConfig({"hedef_hiz_dk": BLOK_HEDEF_HIZ}):
            ayar = core.ayarlari_birlestir(mod._ham_ayarlar(SahteCtx(hedef_hiz_dk=3)))
        self.assertEqual(ayar["hedef_hiz_dk"], BLOK_HEDEF_HIZ,
                         "onaylı eşik masaüstü/ctx değeriyle ezilmemeli")

    def test_ctx_blokta_olmayan_anahtari_doldurur(self):
        """``ctx.get_config`` yalnız yazılmış değeri döndürür; blokta olmayan anahtar ctx'ten gelir."""
        ctx = SahteCtx(kuru_kosu=False, hedef_hiz_dk=3)
        with _SahteHermesConfig({"hedef_hiz_dk": BLOK_HEDEF_HIZ}):
            ayar = core.ayarlari_birlestir(mod._ham_ayarlar(ctx))
        self.assertEqual(ayar["hedef_hiz_dk"], BLOK_HEDEF_HIZ)  # blok kazanır
        self.assertFalse(ayar["kuru_kosu"])                     # blokta yok → ctx doldurdu

    def test_eski_ad_t30_dk_kanonik_ada_cevrilir(self):
        with _SahteHermesConfig(None):
            ayar = core.ayarlari_birlestir(mod._ham_ayarlar(SahteCtx(t30_dk=45)))
        self.assertEqual(ayar["on_bildirim_dk"], 45)

    # ── Önbellek: TTL içinde tekrar okuma aynı sonucu verir ─────────────────────
    def test_ayarlar_ttl_icinde_onbellekten_doner(self):
        # kuru_kosu bloğun bildirmediği anahtar → ctx'ten gelir, TTL etkisi ölçülebilir.
        with _SahteHermesConfig({"hedef_hiz_dk": BLOK_HEDEF_HIZ}):
            ilk = mod._ayarlar(SahteCtx(kuru_kosu=False))
            ikinci = mod._ayarlar(SahteCtx(kuru_kosu=True))  # TTL dolmadı → ctx etkisiz
        self.assertFalse(ilk["kuru_kosu"])
        self.assertFalse(ikinci["kuru_kosu"])
        with mod._kilit:  # TTL sıfırlanınca yeni katman etkili olur
            mod._ayar_onbellek["ts"] = 0.0
        with _SahteHermesConfig({"hedef_hiz_dk": BLOK_HEDEF_HIZ}):
            ucuncu = mod._ayarlar(SahteCtx(kuru_kosu=True))
        self.assertTrue(ucuncu["kuru_kosu"])


class ZincirBeyaniTest(unittest.TestCase):
    """Zincirin BEYANI kodla/``plugin.yaml`` ile ayrışmasın (tek beyan kaynağı kuralı)."""

    def test_katman_sirasi_sabiti_beklenen(self):
        self.assertEqual(
            tuple(core.AYAR_KATMAN_SIRASI),
            ("config.yaml:offpeak-bekci", "ctx.config", "sema_varsayilani"),
        )

    def test_plugin_yaml_katman_sirasini_ayni_beyan_eder(self):
        metin = (KOK / "plugin.yaml").read_text(encoding="utf-8")
        self.assertIn("AYAR_KATMAN_SIRASI", metin, "plugin.yaml beyanı koda atıf vermiyor")
        baslik = metin.index("ETKİN DEĞER SIRASI")
        bolum = metin[baslik:metin.index("\n#\n", baslik)]
        self.assertLess(bolum.index("offpeak-bekci:"), bolum.index("ctx.config"),
                        "plugin.yaml beyanında blok ctx.config'ten önce gelmiyor")
        self.assertLess(bolum.index("ctx.config"), bolum.index("`default`"),
                        "plugin.yaml beyanında ctx.config `default`tan önce gelmiyor")


if __name__ == "__main__":
    unittest.main()
