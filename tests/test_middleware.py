"""``llm_execution`` middleware'i için davranış testi (kuru koşu kapısı).

Neden ayrı dosya: ``bekci_core`` saftır ve ayrı test edilir; burada ise eklenti paketi
(``__init__.py``) üzerinden **middleware** sınanır: gerçekten ``time.sleep`` çağrılıyor mu?
Kapı "kuru" iken çağrılmaması, şartname §5/E5'in test edilebilir karşılığıdır.

Test hermetiktir: ayarlar ``ctx`` ile verilir, günlük geçici dizine yazılır, enjekte edilen
saat/patch'ler ``finally`` ile geri alınır. **Canlı ``config.yaml`` okunmaz** — bu bir
zorunluluktur, süs değil: etkin ayar sırası ``config.yaml:offpeak-bekci`` > ``ctx.config`` >
şema varsayılanı'dır (şartname W4a-1) ve makinenin bloğu ``kuru_kosu: true`` beyan ettiği sürece
ctx ile verilen ``kuru_kosu: False`` **ezilir** → kontrol koşumu sessizce kuru koşuya döner ve
"kapı ölü değil" kontrolü kaybolur (ölçüldü 16.10.2026: ``0 != 5``; ham kanıt
``~/MacAir/offpeak-bekci-K006-olcum-ham-20261016.txt`` H1). Bu yüzden her koşum
``_SahteHermesConfig`` ile canlı bloğu **boş** gösterir; gerçek zincir
``tests/test_ayar_zinciri.py``de sınanır. Aynı sızma ``tools/kuru_kosu_olcum.py``nin E5
kontrol kolunda da vardı → ora da aynı sahteyi kullanır.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import time
import types
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


class _SahteHermesConfig:
    """``hermes_cli.config.load_config_readonly`` sahtesi — kurulum gerekmez, canlı sızmaz.

    ``_SahteHermesConfig({})``: canlı ``config.yaml``ın ``offpeak-bekci:`` bloğunu **boş**
    gösterir → ayarlar ctx katmanından gelir (``tests/test_ayar_zinciri.py`` ile aynı desen,
    orada üç katmanın sırası da ayrıca ölçülür).
    """

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

    def _kosum(self, n: int, ad: str, blok=None, **ayarlar):
        """``n`` çağrılık koşum: canlı ``config.yaml`` bloğu KAPALI (hermetik), ayarlar ctx'ten."""
        gunluk = self.gecici / f"{ad}.jsonl"
        mw = mod._gecikme_kapisi(SahteBaglam(olcum_dosyasi=str(gunluk), **ayarlar))
        with _SahteHermesConfig(blok if blok is not None else {}):
            with mod._kilit:  # TTL önbelleği koşum başında tazelensin
                mod._ayar_onbellek["ts"] = 0.0
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
        self.assertNotEqual(son["hedef_hiz_dk"], core.VARSAYILAN_AYARLAR["hedef_hiz_dk"],
                            "değer şema varsayılanından gelmemeli, ctx'ten gelmeli (hermetiklik)")
        self.assertEqual(son["tavan_sn"], 600.0)

    def test_kuru_kosu_kapaliyken_uyku_istenir(self):
        """Kontrol: kuru_kosu=False → aynı yükte uyku istenir (kapı ölü değil).

        Bu kontrol 16.10.2026'da ``0 != 5`` ile düşüyordu; kök neden KOD değil TEST'in
        hermetik olmamasıydı: canlı ``config.yaml`` bloğu ``kuru_kosu: true`` beyan edince
        (W4a-1 sırası: blok > ctx) ctx'in ``False`` değeri eziliyor ve kapı sessizce kuru
        koşuya dönüyordu. Ölçüm: ``~/MacAir/offpeak-bekci-K006-olcum-ham-20261016.txt`` (H1).
        Çözüm: koşum canlı bloğu boş gösterir (``_SahteHermesConfig``) → ctx kazanır.
        """
        kayitlar = self._kosum(20, "canli", kuru_kosu=False, hedef_hiz_dk=15, erteleme_tavani_sn=600.0)
        self.assertEqual(len(self.uykular), 5)  # 20 çağrı - 15 hedef = 5 fazla
        self.assertTrue(all(sn > 0 for sn in self.uykular))
        self.assertEqual(kayitlar[-1]["uygulanacak_sn"], self.uykular[-1])

    def test_blok_beyan_ederse_ctx_ezilir_ve_kapi_uyumaz(self):
        """Katman sırasının middleware'deki karşılığı (şartname W4a-1): canlı blok ``kuru_kosu``
        beyan ediyorsa ctx'in ``False`` değeri **ezilir** → kapı hesaplar ama uyumaz.

        Aynı zamanda ``_SahteHermesConfig``ın gerçekten etkili olduğunun kanıtıdır: blok boş
        iken (bir üstteki test) uyku istenir, blok beyan edince istenmez. İki koşum arasındaki
        tek fark bloktur.
        """
        kayitlar = self._kosum(20, "bloklu", blok={"kuru_kosu": True},
                               kuru_kosu=False, hedef_hiz_dk=15, erteleme_tavani_sn=600.0)
        self.assertEqual(self.uykular, [], "blok beyanı ctx'i ezmeli → uyku istenmemeli")
        self.assertEqual(kayitlar[-1]["kuru_kosu"], True)
        self.assertGreater(kayitlar[-1]["gerekli_sn"], 0.0)

    def test_yerel_ollamaya_dokunulmaz(self):
        """Yerel/LAN Ollama'da pencere kavramı yok → hiç ölçüm/uyku olmamalı."""
        gunluk = self.gecici / "yerel.jsonl"
        mw = mod._gecikme_kapisi(SahteBaglam(olcum_dosyasi=str(gunluk)))
        for i in range(10):
            mw({"i": i}, lambda req: "OK", base_url="http://10.0.0.1:11434", model="qwen3:8b")
        self.assertEqual(self.uykular, [])
        self.assertFalse(gunluk.exists(), "yerel çağrı günlüğe bile yazılmamalı")


if __name__ == "__main__":
    unittest.main()
