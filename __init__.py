"""offpeak-bekci — Hermes sunucu tarafı.

Kayıtlar (``plugin.yaml`` beyanıyla birebir aynı olacak şekilde):
  * middleware ``llm_execution`` → :func:`_gecikme_kapisi` (istek ``next_call`` sarması)
  * hook ``on_session_end``      → :func:`_oturum_sonu`
  * komutlar ``/offpeak-durum``, ``/offpeak-onayla``, ``/offpeak-kur``, ``/offpeak-kaldir``
    (manifest'te komut beyan alanı yoktur)

Davranış özeti:
  * Gecikme **yalnız** Ollama Cloud çağrısında, **yalnız** peak penceresinde ve son 60 sn'deki
    çağrı sayısı ``hedef_hiz_dk``'yı aştıysa uygulanır; tavanı ``erteleme_tavani_sn``'dir.
  * Varsayılan ``kuru_kosu: true`` → ölçer, geciktirmez (uygulanacak süre 0).
  * Kota tavanına ilk değen çağrı yerel günlüğe uyarı yazar; istek **iptal edilmez** (ilk sürümde
    blok yok).
  * ``/offpeak-kur`` **opt-in** bir cron işinin planını basar; **kuran eklenti değildir**:
    onaydan (plan hash'i) sonra istek oturuma bırakılır ve işi ajanın kendi cron aracı
    (``cronjob_manage``) kurar. ``/offpeak-kaldir`` aynı kapıyla kaldırır. Eklenti cron
    deposuna (``jobs.json``) hiçbir koşulda **yazmaz** — yalnız okur.
  * Ağ çağrısı yok, telemetri yok, sır okunmaz; yalnız yerel kuyruk dosyası okunur ve kullanıcı
    onay verdiğinde (``/offpeak-onayla``) yazılır.
  * Ölçüm/günlük yazımı ve gecikme hesabı asla çağrıyı bozmaz: tüm hata yutulur, ``next_call``
    istisnası olduğu gibi yukarı çıkar.
  * Arayüz dili: kullanıcıya görünen her metin ``metinler`` kataloğundan gelir — **varsayılan
    İngilizce**, ``dil: tr`` (``plugin.yaml`` → ``config_schema.dil``) ile Türkçe. Makine
    sözleşmeleri dilden BAĞIMSIZDIR: ``/offpeak-durum json`` anahtarları, kuyruk durum
    değerleri (``onaylı``/``koşuldu``…), cron argümanları (``onayla``/``duraklat``) ve iş adı
    (``IS_ADI``) çevrilmez. Türkçe kalanlar bilinçli: kod yorumları/docstring'ler ve
    ``logger.debug`` tanı satırları (kullanıcı yüzeyi değil, geliştirici günlüğü).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import bekci_core as core
from . import bekci_kurulum as kurulum
from . import metinler

logger = logging.getLogger(__name__)

_ID = "offpeak-bekci"
_AYAR_TTL_SN = 30.0  # config.yaml değişikliği en geç bu kadar sonra etkili olur

_kilit = threading.RLock()
_journal_kilit = threading.Lock()
_sayac = core.KayanPencere(float(core.VARSAYILAN_AYARLAR["pencere_sn"]))
_kota_sayac = core.KayanPencere(float(core.VARSAYILAN_AYARLAR["kota_penceresi_sn"]))
_ayar_onbellek: Dict[str, Any] = {"ts": 0.0, "ayar": dict(core.VARSAYILAN_AYARLAR)}


# ── Ayarlar ───────────────────────────────────────────────────────────
def _ham_ayarlar(ctx: Any = None) -> Dict[str, Any]:
    """Ayarları toplar: plugin ayar katmanı, sonra ``config.yaml`` → ``offpeak-bekci:`` bloğu.

    Etkin sıra ``core.AYAR_KATMAN_SIRASI``dır (şartname W4a-1): kurulumun onaylı eşik bloğu
    ``ctx.config`` (``plugins.entries.offpeak-bekci`` → ``settings.*``) katmanını **ezer** — onaylı
    eşiği masaüstü değeri sessizce gevşetmesin. ``ctx.config`` bloğun bildirmediği anahtarları
    doldurur (yazılmamış anahtarın ``ctx.get_config`` çağrısı ``None`` döner, katman boş kalır) ve
    şema varsayılanını ezer. Varsayılanlar ``plugin.yaml`` → ``config_schema``'dan gelir
    (``core.VARSAYILAN_AYARLAR``); burada kullanıcıya özel hiçbir değer sabitlenmez. Eski ad
    ``t30_dk`` (varsa) kanonik ``on_bildirim_dk``'ya çevrilir.
    """
    ham: Dict[str, Any] = {}
    if ctx is not None:
        for anahtar in list(core.VARSAYILAN_AYARLAR) + list(core.AYAR_ALIASLARI):
            try:
                deger = ctx.get_config(anahtar, None)
            except Exception:
                deger = None
            if deger is not None:
                ham[anahtar] = deger
    try:
        from hermes_cli.config import load_config_readonly

        blok = (load_config_readonly() or {}).get(_ID)
        if isinstance(blok, dict):
            ham.update(blok)
    except Exception as exc:  # kurulum bozuksa varsayılanlarla devam
        logger.debug("offpeak-bekci: config okunamadı (%s)", exc)
    return ham


def _ayarlar(ctx: Any = None) -> Dict[str, Any]:
    """Etkin ayarlar (``_AYAR_TTL_SN`` boyunca önbelleklenir)."""
    simdi = time.time()
    with _kilit:
        if simdi - float(_ayar_onbellek["ts"]) < _AYAR_TTL_SN:
            return dict(_ayar_onbellek["ayar"])
    ayar = core.ayarlari_birlestir(_ham_ayarlar(ctx))
    with _kilit:
        _ayar_onbellek["ts"] = simdi
        _ayar_onbellek["ayar"] = dict(ayar)
    return ayar


# ── Günlük (yerel, JSONL) ─────────────────────────────────────────────
def _kaydet(kayit: Dict[str, Any], ayar: Optional[Dict[str, Any]] = None) -> None:
    """Ölçüm/uyarı satırı ekler. Hata yutulur (günlük yazımı çağrıyı bozmaz)."""
    try:
        yol = core.yol_genislet((ayar or {}).get("olcum_dosyasi") or core.VARSAYILAN_AYARLAR["olcum_dosyasi"])
        p = Path(yol)
        p.parent.mkdir(parents=True, exist_ok=True)
        satir = json.dumps({"ts": core.utc().isoformat(), "eklenti": _ID, **kayit}, ensure_ascii=False)
        with _journal_kilit:
            with p.open("a", encoding="utf-8") as f:
                f.write(satir + "\n")
    except Exception as exc:
        logger.debug("offpeak-bekci: günlük yazılamadı (%s)", exc)


# ── Kuyruk dosyası ────────────────────────────────────────────────────
def _kuyruk_yolu(ayar: Dict[str, Any]) -> Path:
    return Path(core.yol_genislet(ayar.get("kuyruk_dosyasi") or core.VARSAYILAN_AYARLAR["kuyruk_dosyasi"]))


def _kuyruk_oku(ayar: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """(kalemler, hata) — dosya yoksa kalem listesi boş, hata dolu döner (hata dili `ayar`dan)."""
    yol = _kuyruk_yolu(ayar)
    dil = metinler.dil_sec(ayar)
    try:
        return core.kuyruk_ayristir(yol.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return [], metinler.t("kuyruk.hata.yok", dil, yol=yol)
    except Exception as exc:
        return [], metinler.t("kuyruk.hata.okunamadi", dil, hata=exc)


# ── Middleware: llm_execution ─────────────────────────────────────────
def _gecikme_kapisi(ctx: Any = None) -> Callable[..., Any]:
    """``llm_execution`` middleware'i üretir (kayıt sırasında ctx'i kapatır)."""

    def llm_execution_gecikme(request: Any, next_call: Callable[[Any], Any], **kw: Any) -> Any:
        try:
            if not core.ollama_bulut_mu(kw.get("provider"), kw.get("base_url"), kw.get("model")):
                return next_call(request)  # yerel/LAN Ollama ya da Ollama dışı → dokunma
            ayar = _ayarlar(ctx)
            simdi = core.utc()
            ts = simdi.timestamp()
            with _kilit:
                _sayac.pencere_sn = float(ayar["pencere_sn"])
                sayi = _sayac.kayit(ts)
                _kota_sayac.pencere_sn = float(ayar["kota_penceresi_sn"])
                kota_sayi = _kota_sayac.kayit(ts)
            plan = core.gecikme_planla(
                simdi, sayi, ayar["hedef_hiz_dk"], ayar["erteleme_tavani_sn"], ayar["kuru_kosu"]
            )
            kota = core.kota_durumu(kota_sayi, ayar["kota_tavani"])
            if plan["uygulanacak_sn"] > 0:
                time.sleep(float(plan["uygulanacak_sn"]))
            if plan["gerekli_sn"] > 0:
                _kaydet({
                    "tur": "gecikme",
                    "pencere": plan["pencere"],
                    "sayi_60sn": plan["sayi_60sn"],
                    "hedef_hiz_dk": plan["hedef_hiz_dk"],
                    "gerekli_sn": plan["gerekli_sn"],
                    "uygulanacak_sn": plan["uygulanacak_sn"],
                    "tavan_sn": plan["erteleme_tavani_sn"],
                    "kuru_kosu": plan["kuru_kosu"],
                    "provider": str(kw.get("provider") or ""),
                    "model": str(kw.get("model") or ""),
                }, ayar)
            if kota["uyari"]:
                _kaydet({
                    "tur": "kota_uyari",
                    "pencere": plan["pencere"],
                    "sayi": kota["sayi"],
                    "tavan": kota["tavan"],
                    "pencere_sn": float(ayar["kota_penceresi_sn"]),
                    "kuru_kosu": plan["kuru_kosu"],
                    "not": metinler.t("kayit.kota_uyari.not", metinler.dil_sec(ayar)),
                }, ayar)
        except Exception as exc:  # ölçüm/gecikme asla çağrıyı bozmaz
            logger.debug("offpeak-bekci: middleware ölçüm hatası (%s)", exc)
        return next_call(request)

    return llm_execution_gecikme


# ── Komutlar ──────────────────────────────────────────────────────────
def _durum_verisi(ctx: Any = None) -> Dict[str, Any]:
    ayar = _ayarlar(ctx)
    simdi = core.utc()
    o = core.ozet(simdi, ayar["on_bildirim_dk"])
    kalemler, hata = _kuyruk_oku(ayar)
    sayilar = core.kuyruk_sayilari(kalemler)
    ts = simdi.timestamp()
    with _kilit:
        son60 = _sayac.sayi(ts)
        kota_sayi = _kota_sayac.sayi(ts)
    veri: Dict[str, Any] = dict(o)
    dil = metinler.dil_sec(ayar)
    ozet = metinler.t(
        "rapor.ozet", dil,
        pencere=o["pencere"].upper(), gelecek=o["gelecek_pencere"], geri_sayim=o["geri_sayim"],
        toplam=sayilar["toplam"], onayli=sayilar["onaylı"], kosuldu=sayilar["koşuldu"],
    )
    if sayilar.get("onay_bekleyen"):
        ozet += metinler.t("rapor.ozet.ek", dil, n=sayilar["onay_bekleyen"])
    veri.update({
        # İnsan/bildirim özeti — YALNIZ doğru sayılar (16.10.2026 düzeltmesi): "N bekliyor" ifadesi
        # `bekleyen` alanından geliyordu ve o alan koşulmuşları da sayıyordu ("4 bekliyor" derken
        # 4 kalem koşulmuştu). Artık toplam/onaylı/koşuldu yazılır, iş bekleyen ayrıca eklenir.
        # Metin dili `dil` ayarından gelir; anahtar/tip sözleşmesi aynı kalır.
        "ozet": ozet,
        "kuyruk": sayilar,
        "kalemler": kalemler,
        "kuru_kosu": bool(ayar["kuru_kosu"]),
        "hedef_hiz_dk": int(ayar["hedef_hiz_dk"]),
        "erteleme_tavani_sn": float(ayar["erteleme_tavani_sn"]),
        "son_60sn": son60,
        "kota": core.kota_durumu(kota_sayi, ayar["kota_tavani"]),
        "kota_penceresi_sn": float(ayar["kota_penceresi_sn"]),
        "kuyruk_dosyasi": str(_kuyruk_yolu(ayar)),
        "kuyruk_dosyasi_var": hata is None,
        "kuyruk_hata": hata,
        # Etkin ayarlar + varsayılanlar: masaüstü yarısı ayarları bu alandan okur
        # (bkz. desktop/kabuk.js → `ayar`), kullanıcı ayarı değiştirince davranış burada görünür.
        "ayar": core.etkin_ayarlar(ayar),
    })
    return veri


def _durum_metni(d: Dict[str, Any], dil: str = metinler.VARSAYILAN_DIL) -> str:
    """İnsan okur özet (markdown) — `/offpeak-durum` varsayılan çıktısı.

    Neden ayrı bir yol: eski davranış tek satır JSON'du ve rozet onu makine olarak okur; ama
    kullanıcı komutu kendisi yazdığında ham JSON **okunamıyor** (ölçüm: 16.10.2026, kullanıcı
    bildirdi: "chat alanında rapor çıktı ama ham json hiçbir şey okuyamadım"). Artık:
    varsayılan = bu rapor, makine çıktısı = `/offpeak-durum json` (rozet bu argümanı geçer).
    Metinler ``dil`` dilinde gelir (varsayılan İngilizce; ``dil: tr`` → Türkçe).
    """
    dil = metinler.dil_sec(dil)
    k = d.get("kuyruk") or {}
    kota = d.get("kota") or {}

    def _kisa(x: Any, n: int = 70) -> str:
        s = " ".join(str(x or "").split())
        return s[:n] + ("…" if len(s) > n else "")

    pencere_satiri = metinler.t(
        "rapor.pencere.temel", dil, pencere=str(d.get("pencere", "")).upper()
    )
    if not d.get("peak_mi"):
        pencere_satiri += metinler.t("rapor.pencere.aktif", dil)
    pencere_satiri += metinler.t(
        "rapor.pencere.sonraki", dil,
        gelecek=d.get("gelecek_pencere"), geri_sayim=d.get("geri_sayim"),
    )

    kuyruk_satiri = metinler.t(
        "rapor.kuyruk", dil,
        toplam=k.get("toplam", 0), onayli=k.get("onaylı", 0), kosuldu=k.get("koşuldu", 0),
        atlandi=k.get("atlandı", 0), bekleyen=k.get("onay_bekleyen", 0),
    )
    if k.get("sahipsiz"):
        kuyruk_satiri += metinler.t("rapor.kuyruk.sahipsiz", dil, n=k.get("sahipsiz"))

    satirlar = [
        metinler.t("rapor.baslik", dil, ozet=d.get("ozet", "")),
        "",
        pencere_satiri,
        kuyruk_satiri,
        metinler.t(
            "rapor.kuru", dil,
            durum=metinler.t("rapor.kuru.acik" if d.get("kuru_kosu") else "rapor.kuru.kapali", dil),
            hiz=d.get("hedef_hiz_dk"), tavan=d.get("erteleme_tavani_sn"),
        ),
        metinler.t(
            "rapor.son60", dil,
            sayi=d.get("son_60sn"), kota=kota.get("sayi"), tavan=kota.get("tavan"),
            uyari=metinler.t("rapor.uyari.var" if kota.get("uyari") else "rapor.uyari.yok", dil),
        ),
    ]

    kalemler = d.get("kalemler") or []
    bekleyen = [x for x in kalemler if str(x.get("durum") or "") not in ("", "koşuldu", "atlandı")]
    if bekleyen:
        satirlar.append(metinler.t(
            "rapor.bekleyenler", dil,
            liste=" · ".join(f"`{x.get('id')}` {_kisa(x.get('metin'), 40)}" for x in bekleyen[:5]),
        ))
        if len(bekleyen) > 5:
            satirlar.append(metinler.t("rapor.bekleyenler.devam", dil, n=len(bekleyen) - 5))
    elif kalemler:
        satirlar.append(metinler.t("rapor.bekleyen.yok", dil))

    yol = d.get("kuyruk_dosyasi")
    if d.get("kuyruk_dosyasi_var"):
        satirlar.append(metinler.t("rapor.defter.ok", dil, yol=yol))
    else:
        satirlar.append(metinler.t(
            "rapor.defter.hata", dil, yol=yol, hata=_kisa(d.get("kuyruk_hata"), 90)
        ))

    satirlar.append("")
    satirlar.append(metinler.t("rapor.makine", dil))
    return "\n".join(satirlar)


def _komut_durum(ctx: Any = None) -> Callable[..., str]:
    """``/offpeak-durum [json]`` — insan okur rapor (varsayılan) veya tek satır JSON (rozet)."""

    def offpeak_durum(raw_args: str = "") -> str:
        d = _durum_verisi(ctx)

        if str(raw_args or "").strip().lower().startswith("json"):
            return json.dumps(d, ensure_ascii=False)

        # Dil canlı ayardan okunur (TTL): `dil` değişince çıktı en geç `_AYAR_TTL_SN` sonra döner.
        return _durum_metni(d, metinler.dil_sec(_ayarlar(ctx)))

    return offpeak_durum


def _komut_onayla(ctx: Any = None) -> Callable[..., str]:
    """``/offpeak-onayla <id,id>`` — kuyruk kalemlerini onaylı yapar (kullanıcı eylemi)."""

    def offpeak_onayla(raw_args: str = "") -> str:
        ayar = _ayarlar(ctx)
        dil = metinler.dil_sec(ayar)
        yol = _kuyruk_yolu(ayar)
        idler = core.id_listesi_coz(raw_args)
        if not idler:
            kalemler, _hata = _kuyruk_oku(ayar)
            bekleyen = [k["id"] for k in kalemler if k.get("durum") != core.ONAYLI]
            return metinler.t(
                "onayla.kullanim", dil, yol=yol,
                idler=", ".join(bekleyen) if bekleyen else metinler.t("onayla.bos", dil),
            )
        try:
            metin = yol.read_text(encoding="utf-8")
        except FileNotFoundError:
            return metinler.t("onayla.dosya_yok", dil, yol=yol)
        except Exception as exc:
            return metinler.t("onayla.okunamadi", dil, yol=yol, hata=exc)
        yeni, degisen = core.kuyruk_onayla(metin, idler)
        if not degisen:
            return metinler.t("onayla.degisen_yok", dil, idler=", ".join(idler))
        gecici = yol.with_name(yol.name + ".tmp")
        try:
            gecici.write_text(yeni, encoding="utf-8")
            os.replace(gecici, yol)  # atomik: yarım dosya bırakmaz
        except Exception as exc:
            return metinler.t("onayla.yazilamadi", dil, yol=yol, hata=exc)
        kalan = core.kuyruk_sayilari(core.kuyruk_ayristir(yeni))
        _kaydet({"tur": "onay", "idler": degisen, "kalan": kalan}, ayar)
        return metinler.t(
            "onayla.basarili", dil, n=len(degisen), idler=", ".join(degisen),
            bekleyen=kalan["bekleyen"], onayli=kalan["onaylı"],
        )

    return offpeak_onayla


# ── Kurulum komutları (opt-in cron işi; eklenti cron deposuna YAZMAZ) ──
def _profil_evi() -> Path:
    """Etkin profilin ev dizini — monitör betiği ve cron deposu buna göre çözülür."""
    try:
        from hermes_constants import get_hermes_home

        return Path(get_hermes_home())
    except Exception as exc:
        logger.debug("offpeak-bekci: profil evi Hermes'ten alınamadı (%s)", exc)
    ham = (os.environ.get("HERMES_HOME") or "").strip()
    return Path(os.path.expanduser(ham)) if ham else Path(os.path.expanduser("~/.hermes"))


def _cron_dosyasi() -> Path:
    """Profil cron deposu (``<profil evi>/cron/jobs.json``) — türetilir, çekirdeğe bağlanılmaz.

    Yol **genel yüzeyden** (``hermes_constants.get_hermes_home()``) türetilir; çekirdeğin
    özel modülü (``cron.jobs``) import EDİLMEZ (katalog kural 9: yalnız genel yüzeyler —
    private import doğrulamada uyarı üretir ve sürümde kırılabilir). Türetme çekirdeğin
    kendi hesabıyla birebir aynıdır: ``cron/jobs.py`` → ``JOBS_FILE = get_hermes_home()/"cron"/"jobs.json"``.
    """
    return _profil_evi() / "cron" / "jobs.json"


def _kurulum_isleri_oku(dil: str = metinler.VARSAYILAN_DIL) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Kurulu cron işlerini **salt okur**.

    ``cron.jobs.load_jobs()`` bilerek kullanılmaz: o çağrı ``ensure_dirs()`` ile dizin açar
    (yan etki). Eklenti yalnız deposu okur; (işler, hata) döner — dosya yoksa hata None'dur
    ("kurulu iş yok" demektir). Hata metni ``dil`` dilinde gelir (varsayılan İngilizce).
    """
    yol = _cron_dosyasi()
    dil = metinler.dil_sec(dil)
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [], None
    except Exception as exc:
        return [], metinler.t("kaldir.cron.okunamadi", dil, yol=yol, hata=exc)
    isler = veri.get("jobs") if isinstance(veri, dict) else veri
    if not isinstance(isler, list):
        return [], metinler.t("kaldir.cron.bicim", dil, yol=yol)
    return [i for i in isler if isinstance(i, dict)], None


def _kur_verisi(ctx: Any = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """(plan, ayar) — plan kurulacak işi tam tanımlar; hiçbir şey kurulmaz/yazılmaz."""
    ayar = _ayarlar(ctx)
    kuyruk = _kuyruk_yolu(ayar)
    monitor = _profil_evi() / "scripts" / kurulum.VARSAYILAN_MONITOR
    plan = kurulum.kurulum_plani(
        ayar,
        kuyruk_yolu=str(kuyruk),
        monitor_yolu=str(monitor),
        monitor_var=monitor.is_file(),
        kuyruk_var=kuyruk.is_file(),
        workdir=str(kuyruk.parent),
        workdir_var=kuyruk.parent.is_dir(),
    )
    return plan, ayar


def _oturuma_birak(ctx: Any, metin: str) -> bool:
    """Onay mesajını oturuma bırakır (varsa). Tüm hata yutulur; False = bırakılamadı."""
    try:
        if ctx is not None and hasattr(ctx, "inject_message"):
            return bool(ctx.inject_message(metin))
    except Exception as exc:
        logger.debug("offpeak-bekci: oturuma bırakılamadı (%s)", exc)
    return False


def _komut_kur(ctx: Any = None) -> Callable[..., str]:
    """``/offpeak-kur [onayla <plan_hash> [duraklat]]`` — opt-in cron işinin planı/kurulumu.

    Argümansız: planı basar (hiçbir şey kurmaz). ``onayla <hash>``: hash **planın kendi
    hash'i** olmalı; tutarsa kurulum isteği oturuma bırakılır (işi ajanın cron aracı kurar).
    ``duraklat``: prova için duraklatılmış kurulum.
    """

    def offpeak_kur(raw_args: str = "") -> str:
        plan, ayar = _kur_verisi(ctx)
        dil = metinler.dil_sec(ayar)
        parcalar = str(raw_args or "").split()
        if not parcalar or parcalar[0] in {"plan", "goster", "göster"}:
            return kurulum.kurulum_bildirimi(plan, dil=dil)
        if parcalar[0] != "onayla":
            return metinler.t("kur.bilinmeyen", dil, arg=parcalar[0], ornek=kurulum.ONAY_ORNEK)
        ozet = kurulum.plan_hash(plan)
        if len(parcalar) < 2:
            return metinler.t("kur.hash_kullanimi", dil, ornek=kurulum.ONAY_ORNEK, ozet=ozet)
        verilen = parcalar[1].strip().lower()
        if verilen != ozet:
            return metinler.t("kur.reddedildi", dil, verilen=verilen, ozet=ozet)
        duraklat = any(p in {"duraklat", "duraklatılmış", "duraklatilmis", "paused"} for p in parcalar[2:])
        parametreler = kurulum.cronjob_parametreleri(plan, paused=duraklat, dil=dil)
        metin = kurulum.enjeksiyon_metni(plan, parametreler, paused=duraklat, dil=dil)
        birakildi = _oturuma_birak(ctx, metin)
        _kaydet({
            "tur": "kur_onay",
            "plan_hash": ozet,
            "varyant": plan["varyant"],
            "zamanlama": plan["zamanlama"],
            "kuyruk": plan["kuyruk"],
            "duraklat": duraklat,
            "oturuma_birakildi": birakildi,
            "kurulum_eklenti_degil": metinler.t("kayit.kurulum_eklenti_degil", dil),
        }, ayar)
        baslik = (
            metinler.t("kur.onay_alindi", dil, ozet=ozet,
                       ek=metinler.t("kur.duraklat.ek", dil) if duraklat else "")
            if birakildi else
            metinler.t("kur.onay_alindi_kanal_yok", dil, ozet=ozet)
        )
        return "\n".join([
            baslik,
            metinler.t("kur.is_satiri", dil) + kurulum.parametre_json(parametreler),
            metinler.t("kurulum.geri_alma", dil),
        ])

    return offpeak_kur


def _komut_kaldir(ctx: Any = None) -> Callable[..., str]:
    """``/offpeak-kaldir [liste | onayla <job_id>]`` — kurulu offpeak işlerini listeler/kaldırır.

    Argümansız: kurulu işleri (id, ad, zamanlama, durum, sonraki koşu) basar. ``onayla <id>``:
    yalnız listedeki bir id kabul edilir (yanlış işi silmemek için); kaldırma isteği oturuma
    bırakılır, işi ajanın cron aracı kaldırır.
    """

    def offpeak_kaldir(raw_args: str = "") -> str:
        dil = metinler.dil_sec(_ayarlar(ctx))
        isler, hata = _kurulum_isleri_oku(dil)
        if hata:
            return metinler.t("kaldir.depo_hata", dil, hata=hata)
        bulunan = kurulum.kurulu_isleri_bul(isler)
        parcalar = str(raw_args or "").split()
        if not parcalar or parcalar[0] in {"liste", "listele", "durum"}:
            return kurulum.kurulu_listesi(bulunan, dil=dil)
        if parcalar[0] != "onayla":
            return metinler.t("kaldir.bilinmeyen", dil, arg=parcalar[0],
                              liste=kurulum.kurulu_listesi(bulunan, dil=dil))
        if len(parcalar) < 2:
            return metinler.t("kaldir.kullanim", dil,
                              liste=kurulum.kurulu_listesi(bulunan, dil=dil))
        hedef = parcalar[1].strip()
        eslesen = [i for i in bulunan if i["id"] == hedef]
        if not eslesen:
            return metinler.t("kaldir.farkli_is", dil, hedef=hedef,
                              liste=kurulum.kurulu_listesi(bulunan, dil=dil))
        is_ = eslesen[0]
        metin = kurulum.kaldirma_enjeksiyon_metni(is_, dil=dil)
        birakildi = _oturuma_birak(ctx, metin)
        _kaydet({
            "tur": "kaldir_onay",
            "job_id": is_["id"],
            "ad": is_["name"],
            "oturuma_birakildi": birakildi,
        }, _ayarlar(ctx))
        baslik = (
            metinler.t("kaldir.onay", dil)
            if birakildi else
            metinler.t("kaldir.onay_kanal_yok", dil)
        )
        return "\n".join([baslik, kurulum.kaldirma_bildirimi(is_, dil=dil)])

    return offpeak_kaldir


# ── Hook: on_session_end ──────────────────────────────────────────────
def _oturum_sonu(
    session_id: str = "", completed: bool = True, interrupted: bool = False, **_: Any
) -> None:
    """Oturum sonunda pencere/kota/kuyruk özetini yerel günlüğe yazar (yan etki: yok)."""
    try:
        ayar = _ayarlar(None)
        veri = _durum_verisi(None)
        _kaydet({
            "tur": "oturum_sonu",
            "session_id": str(session_id or ""),
            "completed": bool(completed),
            "interrupted": bool(interrupted),
            "pencere": veri["pencere"],
            "kalan_sn": veri["kalan_sn"],
            "t30_icerisinde": veri["t30_icerisinde"],
            "kuyruk": veri["kuyruk"],
            "kuru_kosu": veri["kuru_kosu"],
        }, ayar)
    except Exception as exc:
        logger.debug("offpeak-bekci: oturum sonu özeti yazılamadı (%s)", exc)


# ── Kayıt ─────────────────────────────────────────────────────────────
def register(ctx: Any) -> None:
    """PluginContext kayıtları — ``plugin.yaml`` beyanıyla birebir.

    Beyan metinleri (açıklama + ``args_hint``) ``metinler`` kataloğundan gelir ve **yükleme
    anındaki** ``dil`` ayarına göre yazılır (komut çıktıları ise canlı ayarı izler); dil
    değişince arayüz beyanları için eklentinin yeniden yüklenmesi gerekir — diğer manifest
    yüzeyleriyle aynı sınır.
    """
    dil = metinler.dil_sec(_ayarlar(ctx))
    ctx.register_middleware("llm_execution", _gecikme_kapisi(ctx))
    ctx.register_command(
        "offpeak-durum",
        handler=_komut_durum(ctx),
        description=metinler.t("komut.durum.aciklama", dil),
        args_hint=metinler.t("komut.durum.ipucu", dil),
    )
    ctx.register_command(
        "offpeak-onayla",
        handler=_komut_onayla(ctx),
        description=metinler.t("komut.onayla.aciklama", dil),
        args_hint=metinler.t("komut.onayla.ipucu", dil),
    )
    ctx.register_command(
        "offpeak-kur",
        handler=_komut_kur(ctx),
        description=metinler.t("komut.kur.aciklama", dil),
        args_hint=metinler.t("komut.kur.ipucu", dil),
    )
    ctx.register_command(
        "offpeak-kaldir",
        handler=_komut_kaldir(ctx),
        description=metinler.t("komut.kaldir.aciklama", dil),
        args_hint=metinler.t("komut.kaldir.ipucu", dil),
    )
    ctx.register_hook("on_session_end", _oturum_sonu)
