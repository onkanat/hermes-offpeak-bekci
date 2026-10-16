#!/usr/bin/env python3
"""E5 ölçümü: ``kuru_kosu: true`` gerçekten "uyumaz" mı? (20 istek üzerinden)

Ölçütler (şartname §5):
  1. ``kuru_kosu: true`` iken 20 bulut isteğinde ``time.sleep`` **hiç** çağrılmaz,
  2. istek başına ek gecikme **< 5 ms** (middleware'in hesap + günlük yazma maliyeti),
  3. kontrol koşumu: ``kuru_kosu: false`` — aynı yükte uyku **istenir** (> 0). Böylece
     (1)'in "kapı ölü" yüzünden değil, gerçekten kuru koşu olduğu için sağlandığı görülür.
     Kontrol kolu canlı ``offpeak-bekci`` bloğunu **boş** gösterir (``SahteHermesConfig``):
     blok ``kuru_kosu: true`` beyan ettiği sürece ctx'in ``false``'u ezilir (W4a-1 sırası) ve
     kontrol yanlış negatif verirdi (ölçüldü 16.10.2026: 0 uyku → "KALDI").

Neden saat enjekte edilir: gece dışı (off-peak) bir saatte koşulursa ``gerekli_sn`` zaten 0
olurdu ve ölçüm hiçbir şeyi kanıtlamazdı. Bu yüzden ``core.utc`` sabit bir **peak** anına
(Pazartesi 13:00 UTC) bağlanır.

Gerçek uyku uyunmaz: ``time.sleep`` taklit edilir, çağrılar ve süreler kaydedilir.

Çalıştırma (hermes_cli'nin bulunduğu yorumlayıcı ile; venv yolu kişiden kişiye değişir):
  HERMES_HOME=~/.hermes ~/.hermes/hermes-agent/venv/bin/python tools/kuru_kosu_olcum.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import time
import types
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
ISTEK_SAYISI = 20
BULUT = dict(provider="ollama-cloud", base_url="https://ollama.com/v1", model="gpt-oss:120b")


def _yukle():
    """Eklenti paketini (dizin adı tireli olduğu için) dosyadan yükler."""
    spec = importlib.util.spec_from_file_location(
        "offpeak_bekci", KOK / "__init__.py", submodule_search_locations=[str(KOK)]
    )
    assert spec is not None and spec.loader is not None, "eklenti paketi yüklenemedi"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["offpeak_bekci"] = mod
    spec.loader.exec_module(mod)
    return mod


class SahteBaglam:
    """``ctx.get_config`` yerine geçer: yalnızca verilen anahtarları ezer."""

    def __init__(self, **ayarlar):
        self.ayarlar = ayarlar

    def get_config(self, anahtar, varsayilan=None):
        return self.ayarlar.get(anahtar, varsayilan)


class SahteHermesConfig:
    """``hermes_cli.config.load_config_readonly`` sahtesi (kurulum gerekmez).

    Kontrol kolu için şart: etkin ayar sırası ``config.yaml:offpeak-bekci`` > ``ctx.config`` >
    şema varsayılanı'dır (şartname W4a-1). Canlı blok ``kuru_kosu: true`` beyan ettiği sürece
    ctx'in ``kuru_kosu=False`` değeri **ezilir**; o zaman (B) kontrolü yanlış negatif verir:
    "uyku çağrısı = 0" — kapı ölü sanılır, oysa kuru koşudadır (ölçüldü 16.10.2026, aynı koşum
    ``SONUÇ: KALDI``). ``SahteHermesConfig({})`` bloğu boş gösterir → ctx kazanır.
    Aynı desen: ``tests/test_ayar_zinciri.py`` · ``tests/test_middleware.py``.
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


class Gunluk:
    """Middleware hataları ``logger.debug`` ile YUTULUR; sessizce ölçüm yapmamak için
    bu mesajlar toplanır ve koşum sonunda boş olmaları şart koşulur."""

    def __init__(self):
        self.mesajlar = []

    def debug(self, mesaj, *args):
        try:
            self.mesajlar.append(str(mesaj) % args if args else str(mesaj))
        except Exception:
            self.mesajlar.append(str(mesaj))


def _sifirla(mod) -> None:
    """Önbellek ve sayaçları temizle (iki koşum birbirini etkilemesin)."""
    mod._ayar_onbellek["ts"] = 0.0
    mod._sayac.sifirla()
    mod._kota_sayac.sifirla()


def _kosum(mod, ctx, uykular, journal: Path, n: int = ISTEK_SAYISI):
    mw = mod._gecikme_kapisi(ctx)
    cagri = lambda req: "YANIT"  # noqa: E731 (ölçüm amaçlı sahte alt çağrı)
    sureler = []
    for i in range(n):
        t0 = time.perf_counter()
        mw({"i": i}, cagri, **BULUT)
        sureler.append((time.perf_counter() - t0) * 1000.0)
    kayitlar = []
    if journal.exists():
        kayitlar = [json.loads(s) for s in journal.read_text(encoding="utf-8").splitlines() if s.strip()]
    return sureler, kayitlar


def _taban(n: int = ISTEK_SAYISI):
    """Karşılaştırma tabanı: aynı döngünün middleware'siz maliyeti."""
    cagri = lambda req: "YANIT"  # noqa: E731
    sureler = []
    for i in range(n):
        t0 = time.perf_counter()
        cagri({"i": i})
        sureler.append((time.perf_counter() - t0) * 1000.0)
    return sureler


def main() -> int:
    try:
        from hermes_cli.config import load_config_readonly
    except Exception as exc:  # yorumlayıcı yanlışsa ölçüm anlamsız → yüksek sesle dur
        print(f"HATA: hermes_cli yüklenemedi ({exc}) — doğru yorumlayıcıyla koşun.", file=sys.stderr)
        return 2

    mod = _yukle()
    core = mod.core
    gunluk = Gunluk()
    setattr(mod, "logger", gunluk)  # yutulan hatalar burada birikir

    blok = (load_config_readonly() or {}).get("offpeak-bekci") or {}
    print(f"config yolu      : {os.environ.get('HERMES_HOME') or '(varsayılan ~/.hermes)'}")
    print(f"offpeak-bekci    : {json.dumps(blok, ensure_ascii=False)}")
    if not blok:
        print("HATA: config'de offpeak-bekci bloğu görünmüyor.", file=sys.stderr)
        return 2

    peak_an = core._dt.datetime(2026, 10, 19, 13, 0, 0, tzinfo=core._dt.timezone.utc)
    # `core.utc` bir saat DEĞİL, normalleştiricidir: `utc()` → şimdi, `utc(dt)` → dt'yi UTC'ye
    # çevirir. Bu yüzden argümanlı çağrılar özgün işleve, argümansız çağrılar sabit peak anına gider.
    _ozgun_utc = core.utc
    core.utc = lambda simdi=None: peak_an if simdi is None else _ozgun_utc(simdi)
    etkin = core.ayarlari_birlestir(mod._ham_ayarlar(None))
    print(
        "etkin ayar       : "
        f"pencere_sn={etkin['pencere_sn']} hedef_hiz_dk={etkin['hedef_hiz_dk']} "
        f"erteleme_tavani_sn={etkin['erteleme_tavani_sn']} kuru_kosu={etkin['kuru_kosu']}"
    )

    gecici = Path(tempfile.mkdtemp(prefix="offpeak-olcum-"))
    gercek_uyku = time.sleep

    sonuc = {}
    try:
        time.sleep = lambda sn: UYKULAR.append(float(sn))  # uyku taklidi

        # ── A) kuru_kosu: true (canlı config) ─────────────────────────────
        UYKULAR = []
        _sifirla(mod)
        j_a = gecici / "kuru.jsonl"
        sureler_a, kayitlar_a = _kosum(mod, SahteBaglam(olcum_dosyasi=str(j_a)), UYKULAR, j_a)
        sonuc["kuru"] = {
            "istek": ISTEK_SAYISI,
            "uyku_cagrisi": len(UYKULAR),
            "uyku_sn_toplam": round(sum(UYKULAR), 3),
            "ms_ort": round(sum(sureler_a) / len(sureler_a), 3),
            "ms_max": round(max(sureler_a), 3),
            "kayit": kayitlar_a[-1] if kayitlar_a else None,
        }
        # ── B) kontrol: kuru_kosu=false ───────────────────────────────────
        # Canlı blok KAPATILMAZSA kontrol yanlış negatif verir: blok `kuru_kosu: true`
        # beyan ettiği sürece ctx'in `false`'u ezilir (W4a-1 sırası) ve kapı "ölü" görünür.
        UYKULAR = []
        _sifirla(mod)
        j_b = gecici / "kont.jsonl"
        # TEK değişken farkı: `kuru_kosu`. Eşikler A koluyla aynı verilir (aksi hâlde
        # "aynı yükte" iddiası gevşek kalır ve tavan varsayılanı devreye girer).
        ctx_b = SahteBaglam(
            kuru_kosu=False,
            olcum_dosyasi=str(j_b),
            hedef_hiz_dk=int(blok.get("hedef_hiz_dk", core.VARSAYILAN_AYARLAR["hedef_hiz_dk"])),
            erteleme_tavani_sn=float(
                blok.get("erteleme_tavani_sn", core.VARSAYILAN_AYARLAR["erteleme_tavani_sn"])
            ),
        )
        with SahteHermesConfig({}):
            sureler_b, kayitlar_b = _kosum(mod, ctx_b, UYKULAR, j_b)
        sonuc["kontrol"] = {
            "istek": ISTEK_SAYISI,
            "uyku_cagrisi": len(UYKULAR),
            "uyku_sn_toplam": round(sum(UYKULAR), 3),
            "son_uyku_sn": UYKULAR[-1] if UYKULAR else 0.0,
            "kayit": kayitlar_b[-1] if kayitlar_b else None,
        }
        taban = _taban()
    finally:
        time.sleep = gercek_uyku

    ek = [a - b for a, b in zip(sureler_a, taban)]
    sonuc["ek_gecikme_ms"] = {
        "ort": round(sum(ek) / len(ek), 3),
        "max": round(max(ek), 3),
        "taban_ms_ort": round(sum(taban) / len(taban), 3),
    }
    sonuc["yutulan_hata"] = gunluk.mesajlar

    print("\nA) kuru_kosu=true (canlı config):")
    print(
        f"   uyku çağrısı = {sonuc['kuru']['uyku_cagrisi']} | ek gecikme ort/max = "
        f"{sonuc['ek_gecikme_ms']['ort']}/{sonuc['ek_gecikme_ms']['max']} ms | "
        f"günlük: {json.dumps(sonuc['kuru']['kayit'], ensure_ascii=False)}"
    )
    print("B) kontrol kuru_kosu=false:")
    print(
        f"   uyku çağrısı = {sonuc['kontrol']['uyku_cagrisi']} | son istenen = "
        f"{sonuc['kontrol']['son_uyku_sn']} sn | günlük: "
        f"{json.dumps(sonuc['kontrol']['kayit'], ensure_ascii=False)}"
    )

    gecti = (
        sonuc["kuru"]["uyku_cagrisi"] == 0
        and sonuc["kuru"]["ms_max"] < 5.0
        and sonuc["kontrol"]["uyku_cagrisi"] > 0
        and (sonuc["kuru"]["kayit"] or {}).get("uygulanacak_sn") == 0.0
        and (sonuc["kuru"]["kayit"] or {}).get("gerekli_sn", 0) > 0
        # A kolu canlı blokla koşar → blok bir değer beyan ediyorsa günlükte O görünmeli
        # (aksi hâlde "canlı config ile ölçüldü" iddiası kanıtsız kalır).
        and (blok.get("hedef_hiz_dk") is None
             or (sonuc["kuru"]["kayit"] or {}).get("hedef_hiz_dk") == int(blok["hedef_hiz_dk"]))
        and not gunluk.mesajlar  # yutulan hata varsa ölçüm geçersiz
    )
    if gunluk.mesajlar:
        print("\nYUTULAN HATALAR (ölçüm geçersiz sayılır):")
        for m in gunluk.mesajlar[:5]:
            print("  -", m)
    print(f"\nSONUÇ: {'GEÇTİ' if gecti else 'KALDI'}")
    print(json.dumps(sonuc, ensure_ascii=False, indent=2))
    return 0 if gecti else 1


if __name__ == "__main__":
    raise SystemExit(main())
