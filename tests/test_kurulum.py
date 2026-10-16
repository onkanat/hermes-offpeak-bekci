"""Kurulum komutları testi (`/offpeak-kur`, `/offpeak-kaldir` — Kanban t_12e1f1e0, W4b).

Neyi kanıtlar:
  * Plan, kurulacak işi **tam** gösterir (iş adı, zamanlama, prompt, monitör, workdir,
    araç kümeleri, teslim) ve onay planın kendi ``plan_hash``ine bağlıdır; hash tutmazsa
    komut kurmaz.
  * Onaydan sonra eklenti işi **kurmaz**: yalnız isteği oturuma bırakır (``inject_message``) ve
    parametreleri ajanın cron aracına verilecek JSON olarak basar.
  * Eklenti cron deposuna (``jobs.json``) **yazmaz**: komut çıktıları ve depo okuması öncesi/
    sonrası dosya içeriği bayt bayt aynıdır.
  * Kaldırma yalnız listedeki bir id ile ve onayla yapılır; yanlış id reddedilir.
  * Plan şablonuna kullanıcıya özel hiçbir yol/değer gömülmez.

Hermetik: gerçek ``config.yaml`` ve gerçek cron deposu okunmaz — ``_ayarlar``, ``_profil_evi``,
``_cron_dosyasi`` ve ``_kaydet`` sahte/tmp değerlerle değiştirilir.

Çalıştırma: `python3 -m unittest discover -s tests -t . -v`
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

KOK = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "offpeak_bekci_kurulum_test", KOK / "__init__.py", submodule_search_locations=[str(KOK)]
)
assert _spec is not None and _spec.loader is not None
mod = importlib.util.module_from_spec(_spec)
sys.modules["offpeak_bekci_kurulum_test"] = mod
_spec.loader.exec_module(mod)

core = mod.core
kur = mod.kurulum

#: Kullanıcıya özel hiçbir yolda geçmemesi gereken imler (eklenti genel bir araçtır).
KISISEL_IMLER = ("MacAir", "/Users/")

ONAY_ISARETI = "onayla"


def _ayar_uret(tmp: Path, **degisiklik) -> dict:
    """Tmp dizine bağlı etkin ayarlar (defter ve günlük tmp'de kalır)."""
    ayar = dict(core.VARSAYILAN_AYARLAR)
    ayar.update({
        "kuyruk_dosyasi": str(tmp / "kuyruk.md"),
        "olcum_dosyasi": str(tmp / "olcum.jsonl"),
    })
    ayar.update(degisiklik)
    return ayar


class SahteBaglam:
    """Kurulum komutlarının gördüğü en küçük bağlam: ayar + oturuma bırakma kaydı."""

    def __init__(self, ayar: dict | None = None, birakildi: bool = True):
        self.ayar = dict(ayar or {})
        self.birakildi = birakildi
        self.birakilanlar: list = []

    def get_config(self, anahtar: str, varsayilan=None):
        return self.ayar.get(anahtar, varsayilan)

    def inject_message(self, metin: str, role: str = "user") -> bool:
        self.birakilanlar.append(metin)
        return self.birakildi


class KurulumOrtami:
    """Tmp profil evi + ayar + kayıt tutucu; komut koşuları için ortak kurulum."""

    def __init__(self, monitor: bool = True, kuyruk: bool = True, isler: list | None = None):
        self.yigin = tempfile.TemporaryDirectory()
        self.kok = Path(self.yigin.name)
        self.ev = self.kok / "profil"
        self.defter = self.kok / "kuyruk.md"
        (self.ev / "cron").mkdir(parents=True)
        if monitor:
            (self.ev / "scripts").mkdir(parents=True)
            (self.ev / "scripts" / kur.VARSAYILAN_MONITOR).write_text("# monitör\n", encoding="utf-8")
        if kuyruk:
            self.defter.write_text("- id: K-001 · durum: onaylı\n", encoding="utf-8")
        self.cron_dosyasi = self.ev / "cron" / "jobs.json"
        self.isler = list(isler or [])
        if isler is not None:
            self.cron_yaz()
        self.ayar = _ayar_uret(self.kok, kuyruk_dosyasi=str(self.defter))
        self.kayitlar: list = []
        self.baglam = SahteBaglam(self.ayar)
        self._yigin = contextlib.ExitStack()
        self._yigin.enter_context(mock.patch.object(mod, "_ayarlar", side_effect=lambda ctx=None: dict(self.ayar)))
        self._yigin.enter_context(mock.patch.object(mod, "_profil_evi", side_effect=lambda: self.ev))
        self._yigin.enter_context(mock.patch.object(mod, "_cron_dosyasi", side_effect=lambda: self.cron_dosyasi))
        self._yigin.enter_context(
            mock.patch.object(mod, "_kaydet", side_effect=lambda kayit, ayar=None: self.kayitlar.append(dict(kayit)))
        )

    def cron_yaz(self) -> None:
        self.cron_dosyasi.write_text(
            json.dumps({"jobs": self.isler, "updated_at": "2026-10-16T00:00:00+03:00"}, ensure_ascii=False),
            encoding="utf-8",
        )

    def depo_baytlari(self) -> bytes | None:
        return self.cron_dosyasi.read_bytes() if self.cron_dosyasi.exists() else None

    def __enter__(self) -> "KurulumOrtami":
        return self

    def __exit__(self, *_: object) -> None:
        self._yigin.close()
        self.yigin.cleanup()


def _plan_uret(ortam: KurulumOrtami) -> dict:
    plan, _ayar = mod._kur_verisi(ortam.baglam)
    return plan


def _etiketli_json(metin: str, etiket: str) -> dict:
    """``<etiket>: {…}`` satırındaki JSON'u çözer (çıktı biçimini de sınar)."""
    for satir in metin.splitlines():
        if satir.startswith(etiket):
            return json.loads(satir[len(etiket):].strip())
    raise AssertionError(f"çıktıda '{etiket}' satırı yok")


class PlanTest(unittest.TestCase):
    """Saf plan (dosya/saat yok): alanlar, hash, parametreler, metinler."""

    def setUp(self):
        self.ayar = dict(core.VARSAYILAN_AYARLAR)
        self.kuyruk = "/tmp/ornek-profil/kuyruk.md"

    def _plan(self, **kw):
        return kur.kurulum_plani(self.ayar, kuyruk_yolu=self.kuyruk, **kw)

    def test_plan_kurulacak_isi_tam_gosterir(self):
        plan = self._plan(monitor_var=True, monitor_yolu="/tmp/scripts/offpeak_bekci.py",
                          workdir="/tmp/ornek-profil", kuyruk_var=True)
        for alan in ("is_adi", "zamanlama", "monitor", "workdir", "enabled_toolsets", "teslim",
                     "prompt", "kuyruk", "varyant"):
            self.assertIn(alan, plan)
            self.assertTrue(str(plan[alan]).strip(), f"{alan} boş")
        self.assertEqual(plan["monitor"], kur.VARSAYILAN_MONITOR)
        self.assertEqual(plan["zamanlama"], kur.POLL_ZAMANLAMA)
        self.assertEqual(plan["varyant"], kur.VARYANT_BEKCI)
        self.assertEqual(list(plan["enabled_toolsets"]), list(kur.VARSAYILAN_TOOLSETLER))
        self.assertEqual(plan["teslim"], "local")
        self.assertEqual(plan["uyarilar"], [])

    def test_monitorsuz_varyant_pencere_beyanina_duser_ve_uyarir(self):
        plan = self._plan(monitor_var=False, workdir="/tmp/ornek-profil")
        self.assertEqual(plan["varyant"], kur.VARYANT_ACILIS)
        self.assertEqual(plan["monitor"], "")
        self.assertEqual(plan["zamanlama"], self.ayar["schedule"])
        self.assertTrue(any("monitör" in u for u in plan["uyarilar"]))
        # monitörsüz iş 5 dakikalık poll'a DÜŞMEZ: her tik ajan koşumu olurdu (maliyet tuzağı).
        self.assertNotEqual(plan["zamanlama"], kur.POLL_ZAMANLAMA)

    def test_kuyruk_yoksa_ve_workdir_yoksa_uyarir(self):
        plan = self._plan(monitor_var=True, kuyruk_var=False, workdir="", workdir_var=False)
        uyarilar = " ".join(plan["uyarilar"])
        self.assertIn("kuyruk defteri yok", uyarilar)
        self.assertIn("çalışma dizini yok", uyarilar)

    def test_prompt_kuyruk_yolunu_ve_isareti_tasir(self):
        plan = self._plan(monitor_var=True)
        self.assertIn(self.kuyruk, plan["prompt"])
        self.assertTrue(kur.is_isareti_metni(plan["prompt"]))
        self.assertIn("onaylı", plan["prompt"])  # onaysız kalem koşmaz kuralı promptta
        for im in KISISEL_IMLER:
            self.assertNotIn(im, plan["prompt"])

    def test_modullerde_kisisel_im_yok(self):
        for dosya in (KOK / "bekci_kurulum.py", KOK / "__init__.py"):
            metin = dosya.read_text(encoding="utf-8")
            for im in KISISEL_IMLER:
                self.assertNotIn(im, metin, f"{dosya.name} içinde kullanıcıya özel im: {im}")

    def test_hash_ayni_girdide_ayni_degisende_farkli(self):
        a = self._plan(monitor_var=True, workdir="/tmp/ornek-profil")
        b = self._plan(monitor_var=True, workdir="/tmp/ornek-profil")
        self.assertEqual(kur.plan_hash(a), kur.plan_hash(b))
        c = self._plan(monitor_var=True, workdir="/tmp/baska-dizin")
        self.assertNotEqual(kur.plan_hash(a), kur.plan_hash(c))
        d = kur.kurulum_plani(self.ayar, kuyruk_yolu="/tmp/baska-profil/kuyruk.md", monitor_var=True)
        self.assertNotEqual(kur.plan_hash(a), kur.plan_hash(d))
        self.assertNotEqual(kur.plan_hash(a), kur.plan_hash(self._plan(monitor_var=False)))
        self.assertEqual(len(kur.plan_hash(a)), 8)

    def test_hash_uyarilari_ve_turev_alanlari_saymaz(self):
        """Hash kurulacak işi temsil eder: yalnız uyarı metni değişirse hash sabit kalır."""
        a = self._plan(monitor_var=True, kuyruk_var=True, workdir="/tmp/ornek-profil")
        b = self._plan(monitor_var=True, kuyruk_var=False, workdir="/tmp/ornek-profil")
        self.assertEqual(a["uyarilar"], [])
        self.assertTrue(b["uyarilar"])
        self.assertEqual(kur.plan_hash(a), kur.plan_hash(b))

    def test_parametreler_yalniz_dolu_alanlari_alir(self):
        plan = self._plan(monitor_var=True, workdir="/tmp/ornek-profil", monitor_yolu="/tmp/scripts/x.py")
        p = kur.cronjob_parametreleri(plan)
        self.assertEqual(p["action"], "create")
        self.assertEqual(p["name"], plan["is_adi"])
        self.assertEqual(p["schedule"], plan["zamanlama"])
        self.assertEqual(p["prompt"], plan["prompt"])
        self.assertEqual(p["monitor"], plan["monitor"])
        self.assertEqual(p["workdir"], plan["workdir"])
        self.assertEqual(p["enabled_toolsets"], list(kur.VARSAYILAN_TOOLSETLER))
        self.assertEqual(p["deliver"], plan["teslim"])
        self.assertNotIn("paused", p)
        # boş alanlar gönderilmez: cron aracına boş monitör/workdir geçmek hatalı iş kurar
        bos = kur.cronjob_parametreleri(self._plan(monitor_var=False, workdir="", workdir_var=False))
        self.assertNotIn("monitor", bos)
        self.assertNotIn("workdir", bos)

    def test_duraklat_parametreleri(self):
        p = kur.cronjob_parametreleri(self._plan(monitor_var=True), paused=True)
        self.assertIs(p["paused"], True)
        self.assertTrue(str(p["paused_reason"]).strip())

    def test_kurulum_bildirimi_kurmaz_ve_onay_ister(self):
        plan = self._plan(monitor_var=True, monitor_yolu="/tmp/scripts/offpeak_bekci.py",
                          workdir="/tmp/ornek-profil")
        metin = kur.kurulum_bildirimi(plan)
        self.assertIn("KURULACAK İŞ", metin)
        self.assertIn("henüz hiçbir şey kurulmadı", metin)
        self.assertIn(plan["is_adi"], metin)
        self.assertIn(plan["kuyruk"], metin)
        self.assertIn(kur.POLL_ZAMANLAMA, metin)
        self.assertIn("/tmp/scripts/offpeak_bekci.py", metin)  # monitör yolu görünür
        self.assertIn(plan["prompt"], metin)  # promptun TAMAMI gösterilir
        self.assertIn(f"plan_hash: {kur.plan_hash(plan)}", metin)
        self.assertIn(f"{ONAY_ISARETI} {kur.plan_hash(plan)}", metin)
        self.assertIn("duraklat", metin)
        self.assertIn("jobs.json", metin)  # açıklama: eklenti yazmaz
        self.assertIn("geri alma", metin)

    def test_enjeksiyon_metni_kurulacak_isi_ve_geri_almayi_verir(self):
        plan = self._plan(monitor_var=True, workdir="/tmp/ornek-profil")
        p = kur.cronjob_parametreleri(plan)
        metin = kur.enjeksiyon_metni(plan, p)
        self.assertIn(kur.plan_hash(plan), metin)
        self.assertIn("cronjob_manage", metin)
        self.assertIn("geri alma", metin)
        # JSON satırı tek başına çözülür ve kurulacak işi birebir verir
        cozulen = json.loads([s for s in metin.splitlines() if s.startswith("{")][0])
        self.assertEqual(cozulen, p)

    def test_isaretli_ve_isaretsiz_isler_ayrilir(self):
        isler = [
            {"id": "a1", "name": kur.IS_ADI, "prompt": "… " + kur.ISARET + " …",
             "schedule": {"display": "*/5 * * * *"}, "enabled": True, "state": "scheduled",
             "next_run_at": "2026-10-16T12:00:00+03:00", "monitor_script": kur.VARSAYILAN_MONITOR},
            {"id": "b2", "name": "offpeak-kuyruk-kosusu", "prompt": "elle kurulmuş",
             "schedule_display": "5 18 * * 1-5", "enabled": False, "state": "paused"},
            {"id": "c3", "name": "bellek-snapshot", "prompt": "alakasız iş",
             "schedule_display": "0 */6 * * *", "enabled": True, "state": "scheduled"},
        ]
        bulunan = kur.kurulu_isleri_bul(isler)
        self.assertEqual([i["id"] for i in bulunan], ["a1", "b2"])
        self.assertTrue(bulunan[0]["isaretli"])
        self.assertFalse(bulunan[1]["isaretli"])
        self.assertEqual(bulunan[0]["schedule_display"], "*/5 * * * *")
        self.assertEqual(bulunan[1]["schedule_display"], "5 18 * * 1-5")

    def test_kurulu_listesi_bos_ve_dolu(self):
        self.assertIn("bulunamadı", kur.kurulu_listesi([]))
        bulunan = kur.kurulu_isleri_bul([
            {"id": "a1", "name": kur.IS_ADI, "prompt": kur.ISARET, "schedule_display": "*/5 * * * *",
             "enabled": True, "state": "scheduled", "next_run_at": "2026-10-16T12:00:00+03:00"},
        ])
        metin = kur.kurulu_listesi(bulunan)
        self.assertIn("henüz hiçbir şey kaldırılmadı", metin)
        self.assertIn("a1", metin)
        self.assertIn("2026-10-16T12:00:00+03:00", metin)
        self.assertIn("onayla <job_id>", metin)

    def test_kaldirma_parametreleri_ve_bildirimi(self):
        p = kur.kaldirma_parametreleri("a1")
        self.assertEqual(p, {"action": "remove", "job_id": "a1"})
        is_ = {"id": "a1", "name": kur.IS_ADI, "schedule_display": "*/5 * * * *", "enabled": True,
               "state": "scheduled"}
        bildirim = kur.kaldirma_bildirimi(is_)
        self.assertIn("a1", bildirim)
        self.assertIn("geri alma", bildirim)
        enj = kur.kaldirma_enjeksiyon_metni(is_)
        self.assertIn('"action": "remove"', enj)
        self.assertIn("cronjob_manage", enj)


class KomutTest(unittest.TestCase):
    """Komut uçları: onay kapısı, oturuma bırakma, cron deposuna YAZMAMA."""

    def test_kur_argsiz_plan_basar_hicbir_sey_kurmaz(self):
        with KurulumOrtami() as o:
            onceki = o.depo_baytlari()
            cikti = mod._komut_kur(o.baglam)()
            self.assertIn("KURULACAK İŞ", cikti)
            self.assertIn("henüz hiçbir şey kurulmadı", cikti)
            self.assertEqual(o.baglam.birakilanlar, [])  # onaysız oturuma hiçbir şey bırakılmaz
            self.assertEqual(o.depo_baytlari(), onceki)  # depo değişmedi
            self.assertEqual(o.kayitlar, [])

    def test_kur_yanlis_hash_reddeder(self):
        with KurulumOrtami() as o:
            onceki = o.depo_baytlari()
            cikti = mod._komut_kur(o.baglam)("onayla 00000000")
            self.assertIn("ONAY REDDEDİLDİ", cikti)
            self.assertEqual(o.baglam.birakilanlar, [])
            self.assertEqual(o.depo_baytlari(), onceki)

    def test_kur_hash_verilmezse_kullanimi_soyler(self):
        with KurulumOrtami() as o:
            cikti = mod._komut_kur(o.baglam)("onayla")
            self.assertIn("kullanım", cikti)
            self.assertIn(kur.plan_hash(_plan_uret(o)), cikti)
            self.assertEqual(o.baglam.birakilanlar, [])

    def test_kur_onaylanan_hash_kurulumu_oturuma_birakir(self):
        with KurulumOrtami() as o:
            plan = _plan_uret(o)
            hash_ = kur.plan_hash(plan)
            onceki = o.depo_baytlari()
            cikti = mod._komut_kur(o.baglam)(f"onayla {hash_}")
            self.assertIn("ONAY ALINDI", cikti)
            self.assertIn("oturuma bırakıldı", cikti)
            self.assertEqual(len(o.baglam.birakilanlar), 1)
            enj = o.baglam.birakilanlar[0]
            self.assertIn(hash_, enj)
            self.assertIn("cronjob_manage", enj)
            gonderilen = _etiketli_json(cikti, "kurulacak iş (tek satır JSON):")
            self.assertEqual(gonderilen, kur.cronjob_parametreleri(plan))
            self.assertEqual(gonderilen["schedule"], plan["zamanlama"])
            self.assertEqual(gonderilen["prompt"], plan["prompt"])
            self.assertEqual(o.depo_baytlari(), onceki)  # kurulumu komut YAPMAZ
            self.assertEqual([k["tur"] for k in o.kayitlar], ["kur_onay"])
            self.assertTrue(o.kayitlar[0]["oturuma_birakildi"])
            self.assertEqual(o.kayitlar[0]["plan_hash"], hash_)

    def test_kur_duraklat_provasi(self):
        with KurulumOrtami() as o:
            hash_ = kur.plan_hash(_plan_uret(o))
            cikti = mod._komut_kur(o.baglam)(f"onayla {hash_} duraklat")
            gonderilen = _etiketli_json(cikti, "kurulacak iş (tek satır JSON):")
            self.assertIs(gonderilen["paused"], True)
            self.assertIn("duraklat", cikti)
            self.assertEqual(o.depo_baytlari(), None)  # prova hiçbir dosya yaratmaz

    def test_kur_oturuma_birakilamazsa_parametreyi_basar(self):
        with KurulumOrtami() as o:
            o.baglam.birakildi = False
            cikti = mod._komut_kur(o.baglam)(f"onayla {kur.plan_hash(_plan_uret(o))}")
            self.assertIn("oturuma bırakılamadı", cikti)
            self.assertIn("cronjob_manage", cikti)
            self.assertFalse(o.kayitlar[0]["oturuma_birakildi"])

    def test_kur_monitor_yoksa_varyant_ve_uyari(self):
        with KurulumOrtami(monitor=False) as o:
            plan = _plan_uret(o)
            self.assertEqual(plan["varyant"], kur.VARYANT_ACILIS)
            cikti = mod._komut_kur(o.baglam)()
            self.assertIn("UYARILAR", cikti)
            self.assertIn("monitör betiği bulunamadı", cikti)

    def test_kur_monitor_varsa_ve_depo_yoksa_onay_yine_serbest(self):
        with KurulumOrtami(isler=[]) as o:  # jobs.json var ama boş
            plan = _plan_uret(o)
            self.assertEqual(plan["varyant"], kur.VARYANT_BEKCI)
            self.assertTrue((o.ev / "scripts" / kur.VARSAYILAN_MONITOR).is_file())
            cikti = mod._komut_kur(o.baglam)(f"onayla {kur.plan_hash(plan)}")
            self.assertIn("ONAY ALINDI", cikti)

    def test_kaldir_depo_yokken_bos_liste_verir(self):
        with KurulumOrtami() as o:  # jobs.json hiç yok
            cikti = mod._komut_kaldir(o.baglam)()
            self.assertIn("bulunamadı", cikti)
            self.assertEqual(o.baglam.birakilanlar, [])
            self.assertEqual(o.depo_baytlari(), None)

    def test_kaldir_liste_ve_yanlis_id_reddi(self):
        isler = [
            {"id": "a1", "name": kur.IS_ADI, "prompt": "x " + kur.ISARET, "enabled": True,
             "state": "scheduled", "schedule_display": "*/5 * * * *"},
            {"id": "z9", "name": "bellek-snapshot-macair", "prompt": "alakasız", "enabled": True,
             "state": "scheduled", "schedule_display": "0 */6 * * *"},
        ]
        with KurulumOrtami(isler=isler) as o:
            onceki = o.depo_baytlari()
            liste = mod._komut_kaldir(o.baglam)()
            self.assertIn("a1", liste)
            self.assertNotIn("z9", liste)  # offpeak işi olmayan iş listelenmez
            self.assertIn("eklenti işi", liste)
            red = mod._komut_kaldir(o.baglam)("onayla z9")
            self.assertIn("offpeak işi değil", red)
            self.assertEqual(o.baglam.birakilanlar, [])
            self.assertEqual(o.depo_baytlari(), onceki)

    def test_kaldir_onaylanan_id_kaldirmayi_birakir(self):
        isler = [{"id": "a1", "name": kur.IS_ADI, "prompt": "x " + kur.ISARET, "enabled": True,
                  "state": "scheduled", "schedule_display": "*/5 * * * *"}]
        with KurulumOrtami(isler=isler) as o:
            onceki = o.depo_baytlari()
            cikti = mod._komut_kaldir(o.baglam)("onayla a1")
            self.assertIn("KALDIRMA ONAYI", cikti)
            self.assertIn('"action": "remove"', cikti)
            self.assertEqual(len(o.baglam.birakilanlar), 1)
            self.assertIn('"job_id": "a1"', o.baglam.birakilanlar[0])
            self.assertEqual(o.depo_baytlari(), onceki)  # kaldırmayı komut YAPMAZ
            self.assertEqual([k["tur"] for k in o.kayitlar], ["kaldir_onay"])

    def test_kaldir_depo_bozuksa_kaldirmaz(self):
        with KurulumOrtami(isler=[]) as o:
            o.cron_dosyasi.write_text("{bozuk", encoding="utf-8")
            cikti = mod._komut_kaldir(o.baglam)("onayla a1")
            self.assertIn("okunamadı", cikti)
            self.assertIn("hiçbir şey kaldırılmadı", cikti)
            self.assertEqual(o.baglam.birakilanlar, [])

    def test_kayitli_komutlar_ve_beyan(self):
        """Kayıt: 3 komut + middleware + hook; kurulum komutları da listede."""
        kayitlar: list = []

        class SahteKayit:
            def register_middleware(self, ad, fn=None):
                kayitlar.append(("middleware", ad))

            def register_command(self, ad, handler=None, description="", args_hint=""):
                kayitlar.append(("command", ad))

            def register_hook(self, ad, fn=None):
                kayitlar.append(("hook", ad))

        mod.register(SahteKayit())
        komutlar = [ad for tur, ad in kayitlar if tur == "command"]
        self.assertEqual(komutlar, ["offpeak-durum", "offpeak-onayla", "offpeak-kur", "offpeak-kaldir"])
        self.assertIn(("middleware", "llm_execution"), kayitlar)
        self.assertIn(("hook", "on_session_end"), kayitlar)


class DepoYoluTest(unittest.TestCase):
    """Cron deposu yolu: profil evinden türetilir, çekirdeğin özel modülü import EDİLMEZ.

    Neden: depo yolu ``cron.jobs.JOBS_FILE`` ile de alınabilirdi, ama o özel çekirdek modülüdür
    (katalog kural 9) ve doğrulama uyarısı üretir — sürümde kırılabilir. Türetme, çekirdeğin
    kendi hesabıyla birebir aynı olmalı: ``get_hermes_home()/"cron"/"jobs.json"``.
    """

    def test_depo_yolu_profil_evinden_turetilir(self):
        with mock.patch.object(mod, "_profil_evi", side_effect=lambda: Path("/tmp/ornek-ev")):
            self.assertEqual(mod._cron_dosyasi(), Path("/tmp/ornek-ev/cron/jobs.json"))

    def test_ozel_cekirdek_modulu_import_edilmez(self):
        """``cron.*`` özel çekirdek modülleri hiçbir eklenti modülünde import edilmemeli."""
        import ast

        for dosya in ("__init__.py", "bekci_core.py", "bekci_kurulum.py"):
            tree = ast.parse((KOK / dosya).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    hedefler = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    hedefler = [node.module or ""]
                else:
                    continue
                for hedef in hedefler:
                    self.assertFalse(
                        hedef == "cron" or hedef.startswith("cron."),
                        f"{dosya}: özel çekirdek modülü import edilmiş: {hedef}",
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
