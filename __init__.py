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
    """(kalemler, hata) — dosya yoksa kalem listesi boş, hata dolu döner."""
    yol = _kuyruk_yolu(ayar)
    try:
        return core.kuyruk_ayristir(yol.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return [], f"dosya yok: {yol}"
    except Exception as exc:
        return [], f"okunamadı: {exc}"


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
                    "not": "istek iptal edilmedi; yalnız uyarı kaydı",
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
    veri.update({
        "ozet": (
            f"{o['pencere'].upper()} · {o['gelecek_pencere']} {o['geri_sayim']} sonra · "
            f"kuyruk {sayilar['bekleyen']} bekliyor / {sayilar['onaylı']} onaylı"
        ),
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


def _durum_metni(d: Dict[str, Any]) -> str:
    """İnsan okur özet (markdown) — `/offpeak-durum` varsayılan çıktısı.

    Neden ayrı bir yol: eski davranış tek satır JSON'du ve rozet onu makine olarak okur; ama
    kullanıcı komutu kendisi yazdığında ham JSON **okunamıyor** (ölçüm: 16.10.2026, kullanıcı
    bildirdi: "chat alanında rapor çıktı ama ham json hiçbir şey okuyamadım"). Artık:
    varsayılan = bu rapor, makine çıktısı = `/offpeak-durum json` (rozet bu argümanı geçer).
    """
    k = d.get("kuyruk") or {}
    kota = d.get("kota") or {}

    def _kisa(x: Any, n: int = 70) -> str:
        s = " ".join(str(x or "").split())
        return s[:n] + ("…" if len(s) > n else "")

    satirlar = [
        f"**Off-peak bekçisi** — {d.get('ozet', '')}",
        "",
        f"- **pencere**: şu an **{str(d.get('pencere', '')).upper()}**"
        + (" — off-peak AKTİF" if not d.get("peak_mi") else "")
        + f" · sonraki {d.get('gelecek_pencere')} **{d.get('geri_sayim')}** sonra",
        f"- **kuyruk**: {k.get('toplam', 0)} kalem · {k.get('onaylı', 0)} onaylı · "
        f"{k.get('koşuldu', 0)} koşuldu · {k.get('atlandı', 0)} atlandı"
        + (f" · {k.get('sahipsiz')} sahipsiz" if k.get("sahipsiz") else ""),
        f"- **kuru koşu**: {'AÇIK (yalnız ölçer, geciktirmez)' if d.get('kuru_kosu') else 'KAPALI (gerçekten erteleyebilir)'}"
        f" · hedef hız: {d.get('hedef_hiz_dk')} çağrı/dk · erteleme tavanı: {d.get('erteleme_tavani_sn')} sn",
        f"- **son 60 sn**: {d.get('son_60sn')} LLM çağrısı · kota: {kota.get('sayi')}/{kota.get('tavan')}"
        f" çağrı ({'UYARI VAR' if kota.get('uyari') else 'uyarı yok'})",
    ]

    kalemler = d.get("kalemler") or []
    bekleyen = [x for x in kalemler if str(x.get("durum") or "") not in ("", "koşuldu", "atlandı")]
    if bekleyen:
        satirlar.append("- **onay/iş bekleyenler**: " + " · ".join(
            f"`{x.get('id')}` {_kisa(x.get('metin'), 40)}" for x in bekleyen[:5]))
        if len(bekleyen) > 5:
            satirlar.append(f"  … ve {len(bekleyen) - 5} tane daha")
    elif kalemler:
        satirlar.append("- **onay bekleyen**: yok (tüm kalemler koşuldu/atlandı)")

    yol = d.get("kuyruk_dosyasi")
    if d.get("kuyruk_dosyasi_var"):
        satirlar.append(f"- **kuyruk defteri**: `{yol}` ✓")
    else:
        satirlar.append(f"- **kuyruk defteri**: `{yol}` ✗ OKUNAMADI — {_kisa(d.get('kuyruk_hata'), 90)}")

    satirlar.append("")
    satirlar.append("_makine çıktısı (rozet/otomasyon): `/offpeak-durum json`_")
    return "\n".join(satirlar)


def _komut_durum(ctx: Any = None) -> Callable[..., str]:
    """``/offpeak-durum [json]`` — insan okur rapor (varsayılan) veya tek satır JSON (rozet)."""

    def offpeak_durum(raw_args: str = "") -> str:
        d = _durum_verisi(ctx)

        if str(raw_args or "").strip().lower().startswith("json"):
            return json.dumps(d, ensure_ascii=False)

        return _durum_metni(d)

    return offpeak_durum


def _komut_onayla(ctx: Any = None) -> Callable[..., str]:
    """``/offpeak-onayla <id,id>`` — kuyruk kalemlerini onaylı yapar (kullanıcı eylemi)."""

    def offpeak_onayla(raw_args: str = "") -> str:
        ayar = _ayarlar(ctx)
        yol = _kuyruk_yolu(ayar)
        idler = core.id_listesi_coz(raw_args)
        if not idler:
            kalemler, _hata = _kuyruk_oku(ayar)
            bekleyen = [k["id"] for k in kalemler if k.get("durum") != core.ONAYLI]
            return (
                "kullanım: /offpeak-onayla <id,id>\n"
                f"kuyruk: {yol}\n"
                f"onay bekleyen: {', '.join(bekleyen) if bekleyen else '(yok)'}"
            )
        try:
            metin = yol.read_text(encoding="utf-8")
        except FileNotFoundError:
            return f"kuyruk dosyası yok: {yol} — içeriğini eklenti yazmaz, sen oluştur."
        except Exception as exc:
            return f"kuyruk okunamadı: {yol} ({exc})"
        yeni, degisen = core.kuyruk_onayla(metin, idler)
        if not degisen:
            return f"değişen kalem yok (zaten onaylı ya da bulunamadı): {', '.join(idler)}"
        gecici = yol.with_name(yol.name + ".tmp")
        try:
            gecici.write_text(yeni, encoding="utf-8")
            os.replace(gecici, yol)  # atomik: yarım dosya bırakmaz
        except Exception as exc:
            return f"kuyruk yazılamadı: {yol} ({exc})"
        kalan = core.kuyruk_sayilari(core.kuyruk_ayristir(yeni))
        _kaydet({"tur": "onay", "idler": degisen, "kalan": kalan}, ayar)
        return (
            f"onaylandı ({len(degisen)}): {', '.join(degisen)} · "
            f"kuyruk {kalan['bekleyen']} bekliyor / {kalan['onaylı']} onaylı"
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


def _kurulum_isleri_oku() -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Kurulu cron işlerini **salt okur**.

    ``cron.jobs.load_jobs()`` bilerek kullanılmaz: o çağrı ``ensure_dirs()`` ile dizin açar
    (yan etki). Eklenti yalnız deposu okur; (işler, hata) döner — dosya yoksa hata None'dur
    ("kurulu iş yok" demektir).
    """
    yol = _cron_dosyasi()
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [], None
    except Exception as exc:
        return [], f"cron deposu okunamadı: {yol} ({exc})"
    isler = veri.get("jobs") if isinstance(veri, dict) else veri
    if not isinstance(isler, list):
        return [], f"cron deposu beklenmeyen biçimde: {yol}"
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
        parcalar = str(raw_args or "").split()
        if not parcalar or parcalar[0] in {"plan", "goster", "göster"}:
            return kurulum.kurulum_bildirimi(plan)
        if parcalar[0] != "onayla":
            return (
                f"bilinmeyen argüman: {parcalar[0]}\n"
                f"kullanım: {kurulum.ONAY_ORNEK}\nplanı göster: /offpeak-kur"
            )
        ozet = kurulum.plan_hash(plan)
        if len(parcalar) < 2:
            return (
                f"kullanım: {kurulum.ONAY_ORNEK}\n"
                f"plan_hash: {ozet}\n"
                "onay planın kendi hash'ini ister (yanlışlıkla kurulumu önler)."
            )
        verilen = parcalar[1].strip().lower()
        if verilen != ozet:
            return (
                "ONAY REDDEDİLDİ — plan hash'i tutmuyor, hiçbir şey kurulmadı.\n"
                f"  verilen    : {verilen}\n  plan_hash  : {ozet}\n"
                "plan bu arada değişmiş olabilir (ayar/kuyruk yolu): `/offpeak-kur` ile yeniden bak."
            )
        duraklat = any(p in {"duraklat", "duraklatılmış", "duraklatilmis", "paused"} for p in parcalar[2:])
        parametreler = kurulum.cronjob_parametreleri(plan, paused=duraklat)
        metin = kurulum.enjeksiyon_metni(plan, parametreler, paused=duraklat)
        birakildi = _oturuma_birak(ctx, metin)
        _kaydet({
            "tur": "kur_onay",
            "plan_hash": ozet,
            "varyant": plan["varyant"],
            "zamanlama": plan["zamanlama"],
            "kuyruk": plan["kuyruk"],
            "duraklat": duraklat,
            "oturuma_birakildi": birakildi,
            "kurulum_eklenti_degil": "işi ajanın cron aracı kurar",
        }, ayar)
        baslik = (
            f"ONAY ALINDI (plan {ozet}{' · duraklatılmış' if duraklat else ''}) — kurulum isteği "
            "oturuma bırakıldı; işi ajanın cron aracı kurar (eklenti jobs.json'a yazmaz)."
            if birakildi else
            f"ONAY ALINDI (plan {ozet}) — bu kanalda oturuma bırakılamadı; aşağıdaki parametreyi "
            "ajana ver ya da `cronjob_manage` ile kendin kur."
        )
        return "\n".join([
            baslik,
            "kurulacak iş (tek satır JSON): " + kurulum.parametre_json(parametreler),
            kurulum.GERI_ALMA,
        ])

    return offpeak_kur


def _komut_kaldir(ctx: Any = None) -> Callable[..., str]:
    """``/offpeak-kaldir [liste | onayla <job_id>]`` — kurulu offpeak işlerini listeler/kaldırır.

    Argümansız: kurulu işleri (id, ad, zamanlama, durum, sonraki koşu) basar. ``onayla <id>``:
    yalnız listedeki bir id kabul edilir (yanlış işi silmemek için); kaldırma isteği oturuma
    bırakılır, işi ajanın cron aracı kaldırır.
    """

    def offpeak_kaldir(raw_args: str = "") -> str:
        isler, hata = _kurulum_isleri_oku()
        if hata:
            return f"{hata}\nhiçbir şey kaldırılmadı (eklenti cron deposuna yazmaz)."
        bulunan = kurulum.kurulu_isleri_bul(isler)
        parcalar = str(raw_args or "").split()
        if not parcalar or parcalar[0] in {"liste", "listele", "durum"}:
            return kurulum.kurulu_listesi(bulunan)
        if parcalar[0] != "onayla":
            return (
                f"bilinmeyen argüman: {parcalar[0]}\n"
                "kullanım: /offpeak-kaldir onayla <job_id> · liste için: /offpeak-kaldir\n\n"
                + kurulum.kurulu_listesi(bulunan)
            )
        if len(parcalar) < 2:
            return (
                "kullanım: /offpeak-kaldir onayla <job_id>\n\n" + kurulum.kurulu_listesi(bulunan)
            )
        hedef = parcalar[1].strip()
        eslesen = [i for i in bulunan if i["id"] == hedef]
        if not eslesen:
            return (
                f"bu id bu profilde bir offpeak işi değil: {hedef} — hiçbir şey kaldırılmadı.\n"
                "kaldırma yalnız aşağıdaki listedeki id'lerle yapılır.\n\n"
                + kurulum.kurulu_listesi(bulunan)
            )
        is_ = eslesen[0]
        metin = kurulum.kaldirma_enjeksiyon_metni(is_)
        birakildi = _oturuma_birak(ctx, metin)
        _kaydet({
            "tur": "kaldir_onay",
            "job_id": is_["id"],
            "ad": is_["name"],
            "oturuma_birakildi": birakildi,
        }, _ayarlar(ctx))
        baslik = (
            "KALDIRMA ONAYI — istek oturuma bırakıldı; işi ajanın cron aracı kaldırır."
            if birakildi else
            "KALDIRMA ONAYI — bu kanalda oturuma bırakılamadı; aşağıdaki parametreyi ajana ver."
        )
        return "\n".join([baslik, kurulum.kaldirma_bildirimi(is_)])

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
    """PluginContext kayıtları — ``plugin.yaml`` beyanıyla birebir."""
    ctx.register_middleware("llm_execution", _gecikme_kapisi(ctx))
    ctx.register_command(
        "offpeak-durum",
        handler=_komut_durum(ctx),
        description="Ollama off-peak penceresi, geri sayım, kota ve kuyruk durumu (okunur rapor; `json` ile makine çıktısı).",
        args_hint="[json]",
    )
    ctx.register_command(
        "offpeak-onayla",
        handler=_komut_onayla(ctx),
        description="Off-peak kuyruğundaki iş kalemlerini onaylı yapar (kullanıcı onayı).",
        args_hint="<id,id>",
    )
    ctx.register_command(
        "offpeak-kur",
        handler=_komut_kur(ctx),
        description=(
            "Opt-in off-peak cron işinin planını gösterir; `onayla <plan_hash> [duraklat]` ile "
            "kurulum isteğini oturuma bırakır (işi ajanın cron aracı kurar)."
        ),
        args_hint="[onayla <plan_hash> [duraklat]]",
    )
    ctx.register_command(
        "offpeak-kaldir",
        handler=_komut_kaldir(ctx),
        description=(
            "Kurulu offpeak cron işlerini listeler; `onayla <job_id>` ile kaldırma isteğini "
            "oturuma bırakır (işi ajanın cron aracı kaldırır)."
        ),
        args_hint="[onayla <job_id>]",
    )
    ctx.register_hook("on_session_end", _oturum_sonu)
