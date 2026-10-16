"""offpeak-bekci — Hermes sunucu tarafı.

Kayıtlar (``plugin.yaml`` beyanıyla birebir aynı olacak şekilde):
  * middleware ``llm_execution`` → :func:`_gecikme_kapisi` (istek ``next_call`` sarması)
  * hook ``on_session_end``      → :func:`_oturum_sonu`
  * komutlar ``/offpeak-durum``, ``/offpeak-onayla`` (manifest'te komut beyan alanı yoktur)

Davranış özeti:
  * Gecikme **yalnız** Ollama Cloud çağrısında, **yalnız** peak penceresinde ve son 60 sn'deki
    çağrı sayısı ``hedef_hiz_dk``'yı aştıysa uygulanır; tavanı ``erteleme_tavani_sn``'dir.
  * Varsayılan ``kuru_kosu: true`` → ölçer, geciktirmez (uygulanacak süre 0).
  * Kota tavanına ilk değen çağrı yerel günlüğe uyarı yazar; istek **iptal edilmez** (ilk sürümde
    blok yok).
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
    """Ayarları toplar: ``config.yaml`` → ``offpeak-bekci:`` bloğu, sonra plugin ayar katmanı.

    Etkin sıra ``core.AYAR_KATMAN_SIRASI``dır: ``ctx.config`` (``plugins.entries.offpeak-bekci``
    → ``settings.*``) bloğu **ezer** — sunucunun uyguladığı eşik masaüstünün gösterdiği ayardan
    ayrışmasın ve aynı eklenti profil başına farklı eşiklerle çalışabilsin. Blok kurulumun onaylı
    eşikleridir ve şema varsayılanını ezer. Varsayılanlar ``plugin.yaml`` → ``config_schema``'dan
    gelir (``core.VARSAYILAN_AYARLAR``); burada kullanıcıya özel hiçbir değer sabitlenmez. Eski ad
    ``t30_dk`` (varsa) kanonik ``on_bildirim_dk``'ya çevrilir.
    """
    ham: Dict[str, Any] = {}
    try:
        from hermes_cli.config import load_config_readonly

        blok = (load_config_readonly() or {}).get(_ID)
        if isinstance(blok, dict):
            ham.update(blok)
    except Exception as exc:  # kurulum bozuksa varsayılanlarla devam
        logger.debug("offpeak-bekci: config okunamadı (%s)", exc)
    if ctx is not None:
        for anahtar in list(core.VARSAYILAN_AYARLAR) + list(core.AYAR_ALIASLARI):
            try:
                deger = ctx.get_config(anahtar, None)
            except Exception:
                deger = None
            if deger is not None:
                ham[anahtar] = deger
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


def _komut_durum(ctx: Any = None) -> Callable[..., str]:
    """``/offpeak-durum`` — rozetin okuduğu tek satır JSON."""

    def offpeak_durum(raw_args: str = "") -> str:
        return json.dumps(_durum_verisi(ctx), ensure_ascii=False)

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
        description="Ollama off-peak penceresi, geri sayım, kota ve kuyruk durumu (JSON).",
    )
    ctx.register_command(
        "offpeak-onayla",
        handler=_komut_onayla(ctx),
        description="Off-peak kuyruğundaki iş kalemlerini onaylı yapar (kullanıcı onayı).",
        args_hint="<id,id>",
    )
    ctx.register_hook("on_session_end", _oturum_sonu)
