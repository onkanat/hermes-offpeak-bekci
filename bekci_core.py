"""offpeak-bekci — saf çekirdek: pencere matematiği, kuyruk ayrıştırma, gecikme/kota politikası.

Bu modül bilerek yalnızca standart kütüphaneyi kullanır: ağ yok, dosya yok, saat okuma yok.
Her karar fonksiyonu **saf** — "şimdi" parametre olarak girer, aynı girdi aynı çıktıyı verir.
Bu yüzden pencere sınırları, gecikme tavanı ve "pencere başına bir kez" bayrağı gerçek saate
bağlı olmadan test edilebilir (bkz. ``tests/``).

PENCERE TANIMI — kaynak: https://ollama.com/pricing (Ollama Cloud, 16.10.2026'da okundu):
    "Off-peak pricing apply outside 12:00 and 18:00 UTC on weekdays and all day on weekends."
=> peak = hafta içi (Pazartesi–Cuma) 12:00–18:00 UTC; kalan her saat + hafta sonunun tamamı
   = off-peak.

KOTA GERÇEĞİ (aynı sayfa): faturalama kredi ile (Pro 60 $/ay dahil), eşzamanlılık Free 1 /
Pro 3 / Max-Team 10; sınır aşılırsa istek kuyruğa alınır, kuyruk dolarsa reddedilir; %90'da
e-posta uyarısı gider; canlı kullanım ollama.com/settings.

UYARI: delinux01'deki ``deepseek-whale`` eklentisinin ``PEAK_WINDOWS = [[1,4],[6,10]]`` değeri
DeepSeek API'sinin KENDİ takvimidir (kaynak: api-docs.deepseek.com) — bizim sağlayıcımız Ollama
olduğu için burada KULLANILMAZ.
(bkz. tests/test_bekci_core.py::PeakPencereTest.test_deepseek_takvimi_sizmadi)
"""

from __future__ import annotations

import datetime as _dt
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ── Pencere sabitleri (hepsi UTC) ─────────────────────────────────────
PEAK_GUNLER: Tuple[int, ...] = (0, 1, 2, 3, 4)  # Pazartesi=0 … Cuma=4 (datetime.weekday())
PEAK_BASLANGIC_SAAT = 12  # dahil
PEAK_BITIS_SAAT = 18  # hariç
PENCERE_PEAK = "peak"
PENCERE_OFFPEAK = "off-peak"

#: Ayarların tek doğruluk kaynağı; ``config.yaml`` → ``offpeak-bekci:`` bloğu bunları ezer.
VARSAYILAN_AYARLAR: Dict[str, Any] = {
    # Yalnız ölç, geciktirme. Canlıya almak için config.yaml'da kuru_kosu: false.
    "kuru_kosu": True,
    # peak penceresinde dakikada en fazla kaç çağrı (kayan 60 sn penceresi)
    "hedef_hiz_dk": 6,
    # kayan pencerenin uzunluğu (sn)
    "pencere_sn": 60.0,
    # tek bir istek için en fazla bekleme (sn) — gecikmenin tavanı
    "erteleme_tavani_sn": 30.0,
    # kota sayacının penceresi (sn) ve tavanı (çağrı); tavan aşılırsa uyarı kaydı yazılır
    "kota_penceresi_sn": 3600.0,
    "kota_tavani": 120,
    # onay bekleyen kalemlerin listesi (kullanıcı dosyası — eklenti içeriğini yazmaz)
    "kuyruk_dosyasi": "~/MacAir/off-peak-kuyruk.md",
    # ölçüm/uyarı günlüğü (JSONL, yerel; ağ yok)
    "olcum_dosyasi": "~/.hermes/offpeak-bekci/olcum.jsonl",
    # off-peak'e kaç dakika kala hatırlatma penceresi başlar
    "t30_dk": 30,
}


# ── Yardımcılar ───────────────────────────────────────────────────────
def utc(simdi: Optional[_dt.datetime] = None) -> _dt.datetime:
    """Naive datetime'ı UTC kabul eder; aware olanı UTC'ye çevirir."""
    if simdi is None:
        return _dt.datetime.now(_dt.timezone.utc)
    if simdi.tzinfo is None:
        return simdi.replace(tzinfo=_dt.timezone.utc)
    return simdi.astimezone(_dt.timezone.utc)


def _saat_basi(gun: _dt.datetime, saat: int) -> _dt.datetime:
    return gun.replace(hour=saat, minute=0, second=0, microsecond=0)


# ── Pencere fonksiyonları (saf) ───────────────────────────────────────
def peak_mi(simdi: _dt.datetime) -> bool:
    """Hafta içi 12:00–18:00 UTC mi? (12:00 dahil, 18:00 hariç)"""
    s = utc(simdi)
    return s.weekday() in PEAK_GUNLER and PEAK_BASLANGIC_SAAT <= s.hour < PEAK_BITIS_SAAT


def pencere(simdi: _dt.datetime) -> str:
    """``"peak"`` veya ``"off-peak"``."""
    return PENCERE_PEAK if peak_mi(simdi) else PENCERE_OFFPEAK


def sonraki_gecis(simdi: _dt.datetime) -> Tuple[str, _dt.datetime]:
    """(gelecek pencerenin adı, geçiş anı) — her zaman *şimdi*'den sonradır."""
    s = utc(simdi)
    if peak_mi(s):
        # peak'teyiz → off-peak bugün 18:00'de başlar
        return PENCERE_OFFPEAK, _saat_basi(s, PEAK_BITIS_SAAT)
    # off-peak'teyiz → sonraki peak, en yakın hafta içi günün 12:00'si
    aday = _saat_basi(s, PEAK_BASLANGIC_SAAT)
    if aday <= s:
        aday += _dt.timedelta(days=1)
    while aday.weekday() not in PEAK_GUNLER:
        aday += _dt.timedelta(days=1)
    return PENCERE_PEAK, aday


def kalan_saniye(simdi: _dt.datetime) -> int:
    """Gelecek pencere değişimine kalan saniye (tam sayı, aşağı yuvarlı)."""
    _, gecis = sonraki_gecis(simdi)
    return int((gecis - utc(simdi)).total_seconds())


def geri_sayim(simdi: _dt.datetime) -> str:
    """``"HH:MM"`` — dakika yukarı yuvarlanır (00:00 yalnız gerçekten 0'da görünür)."""
    kalan = max(0, kalan_saniye(simdi))
    toplam_dk = -(-kalan // 60)  # ceil
    saat, dk = divmod(toplam_dk, 60)
    return f"{saat:02d}:{dk:02d}"


def offpeak_hatirlatma_mi(simdi: _dt.datetime, t30_dk: int = 30) -> bool:
    """Off-peak'e ``t30_dk`` dakika veya daha az kaldıysa True (yalnız peak'te)."""
    if not peak_mi(simdi):
        return False
    return kalan_saniye(simdi) <= max(0, int(t30_dk)) * 60


def offpeak_anahtari(simdi: _dt.datetime) -> str:
    """İçinde olunan/yaklaşılan off-peak bloğunun kimliği (ISO-8601 UTC).

    "Pencere başına bir kez" bayrağının anahtarıdır: anahtar değiştiyse yeni pencere.
    Off-peak bloğu her hafta içi gün 18:00'de başlar ve hafta sonu boyunca sürer.
    """
    s = utc(simdi)
    if peak_mi(s):
        bas = _saat_basi(s, PEAK_BITIS_SAAT)  # bugün 18:00'de başlayacak
    else:
        bas = _saat_basi(s, PEAK_BITIS_SAAT)  # en son 18:00 sınırı
        if bas > s:
            bas -= _dt.timedelta(days=1)
        while bas.weekday() not in PEAK_GUNLER:
            bas -= _dt.timedelta(days=1)
    return bas.isoformat()


def ozet(simdi: _dt.datetime, t30_dk: int = 30) -> Dict[str, Any]:
    """Rozet/komut için tek çağrıda pencere özeti (saf)."""
    s = utc(simdi)
    gelecek_ad, gelecek_an = sonraki_gecis(s)
    return {
        "pencere": pencere(s),
        "peak_mi": peak_mi(s),
        "gelecek_pencere": gelecek_ad,
        "gelecek_gecis_utc": gelecek_an.isoformat(),
        "kalan_sn": kalan_saniye(s),
        "geri_sayim": geri_sayim(s),
        "t30_dk": int(t30_dk),
        "t30_icerisinde": offpeak_hatirlatma_mi(s, t30_dk),
        "offpeak_anahtari": offpeak_anahtari(s),
    }


# ── Ollama bulut tespiti (saf) ────────────────────────────────────────
_BULUT_ISARETLERI = ("ollama.com", "ollama.ai", "ollama.cloud", "ollama-cloud")
_YEREL_ISARETLERI = (
    "127.0.0.1", "localhost", "0.0.0.0", "::1", ".local", "host.docker.internal",
    "192.168.", "10.0.", "172.16.",
)


def ollama_bulut_mu(
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> bool:
    """Çağrı Ollama **Cloud**'a mı gidiyor?

    Off-peak fiyatlandırması yalnız bulutta vardır; yerel/LAN Ollama'da pencere kavramı yoktur.
    Bu yüzden yerel işaretleri görünce koşulsuz False döneriz (gereksiz gecikme yapmayalım).
    """
    p = str(provider or "").strip().lower()
    u = str(base_url or "").strip().lower()
    m = str(model or "").strip().lower()
    if any(y in u for y in _YEREL_ISARETLERI):
        return False
    if any(b in u for b in _BULUT_ISARETLERI):
        return True
    if any(b in p for b in _BULUT_ISARETLERI):
        return True
    if m.endswith("-cloud") or "-cloud-" in m:
        return True
    return False


# ── Gecikme politikası (saf) ──────────────────────────────────────────
def gecikme_planla(
    simdi: _dt.datetime,
    sayi_60sn: int,
    hedef_hiz_dk: int = 6,
    erteleme_tavani_sn: float = 30.0,
    kuru_kosu: bool = True,
) -> Dict[str, Any]:
    """Bu çağrı için beklenecek süreyi hesaplar (uygulamaz).

    Kural: kayan pencerede ``hedef_hiz_dk``'yı aşan her fazla çağrı, hedef hızda bir "slot"
    kadar bekler → ``gerekli = fazla * (60 / hedef_hiz_dk)``. Gecikme ``erteleme_tavani_sn``
    ile sınırlanır, yalnız **peak** penceresinde uygulanır ve ``kuru_kosu`` ise hiç uygulanmaz
    (istenen süre yine raporlanır).
    """
    hedef = max(1, int(hedef_hiz_dk))
    fazla = max(0, int(sayi_60sn) - hedef)
    gerekli = 0.0 if fazla == 0 else fazla * (60.0 / hedef)
    if not peak_mi(simdi):
        gerekli = 0.0
    tavan = max(0.0, float(erteleme_tavani_sn))
    uygulanacak = 0.0 if kuru_kosu else min(gerekli, tavan)
    return {
        "pencere": pencere(simdi),
        "sayi_60sn": int(sayi_60sn),
        "hedef_hiz_dk": hedef,
        "fazla": fazla,
        "gerekli_sn": round(gerekli, 3),
        "erteleme_tavani_sn": tavan,
        "uygulanacak_sn": round(uygulanacak, 3),
        "kuru_kosu": bool(kuru_kosu),
    }


class KayanPencere:
    """Kayan zaman penceresinde olay sayacı (saf: zaman dışarıdan verilir).

    SINIR SEMANTİĞİ — YARI AÇIK: pencere ``(ts - pencere_sn, ts]``.
    Yani ``sayi(ts)``/``kayit(ts)`` çağrıldığında anı **tam** ``pencere_sn`` saniye önce
    olan kayıt pencere DIŞIdır (``k > ts - pencere_sn``), ``ts`` anındaki kayıt İÇİdedir.
    "Son 60 saniyedeki çağrı" ifadesinin karşılığı budur: 60 saniye önce yapılmış çağrı
    artık o dakikaya ait değildir. (16.10.2026: testin eski beklentisi kapalı sınır
    varsayıyordu — ölçülen değer doğruydu, beklenti düzeltildi.)
    """

    def __init__(self, pencere_sn: float = 60.0) -> None:
        self.pencere_sn = float(pencere_sn)
        self._kayitlar: List[float] = []

    def _budur(self, ts: float) -> None:
        if not self._kayitlar:
            return
        esik = float(ts) - self.pencere_sn
        if self._kayitlar[0] <= esik:  # en eski kayıt pencerenin dışında → süpür
            self._kayitlar = [k for k in self._kayitlar if k > esik]

    def kayit(self, ts: float) -> int:
        """``ts`` anındaki olayı kaydeder; penceredeki toplam sayıyı döner."""
        self._budur(ts)
        self._kayitlar.append(float(ts))
        return len(self._kayitlar)

    def sayi(self, ts: float) -> int:
        self._budur(ts)
        return len(self._kayitlar)

    def sifirla(self) -> None:
        self._kayitlar = []


def kota_durumu(sayi: int, kota_tavani: int) -> Dict[str, Any]:
    """Kota penceresi durumu. ``uyari`` yalnız tavana İLK değen çağrıda True'dur."""
    tavan = max(1, int(kota_tavani))
    return {
        "sayi": int(sayi),
        "tavan": tavan,
        "asildi": int(sayi) >= tavan,
        "uyari": int(sayi) == tavan,
    }


# ── Kuyruk dosyası (saf metin işleme) ─────────────────────────────────
_SATIR_KALEMI = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
_KUTU_ISARETI = re.compile(r"^\[( |x|X)\]\s*(.*)$")
_ID_ALANI = re.compile(r"(?:^|[\s|·;,])(?:id|kimlik)\s*[:=]\s*([^\s|·;,]+)", re.IGNORECASE)
_DURUM_ALANI = re.compile(r"(?:^|[\s|·;,])(?:durum|status)\s*[:=]\s*([^\s|·;,]+)", re.IGNORECASE)
_EFOR_ALANI = re.compile(r"(?:^|[\s|·;,])(?:efor|effort)\s*[:=]\s*([^\s|·;,]+)", re.IGNORECASE)
# Tablo biçimi: `| K-001 | iş | sahip | kanıt | onay-bekliyor | pencere |`
_TABLO_SATIRI = re.compile(r"^\s*\|(.+)\|\s*$")
_TABLO_AYRAC_HUCRE = re.compile(r"^:?-{2,}:?$")
_TABLO_ID = re.compile(r"^`?[A-Za-z]{1,6}-?\d+`?$")
_TABLO_EFOR = re.compile(r"^`?e-\d+`?$", re.IGNORECASE)
_TABLO_BASLIKLARI = {
    "id", "iş", "is", "kalem", "sahip", "owner", "kanıt", "kanit", "kanıt/dosya",
    "durum", "status", "pencere", "efor", "effort", "not", "notlar", "başlık", "baslik",
}

ONAYLI = "onaylı"
BEKLIYOR = "bekliyor"
KOSULDU = "koşuldu"
ATLANDI = "atlandı"
SAHIPSIZ = "sahipsiz"

#: Ham durum sözcüğü → normalleştirilmiş durum (kuyruk dosyasındaki yazım çeşitleri).
_DURUM_ESANLAMLILARI = {
    "onaylı": ONAYLI, "onaylandi": ONAYLI, "onaylandı": ONAYLI, "approved": ONAYLI,
    "ok": ONAYLI, "done": ONAYLI, "tamam": ONAYLI, "onay": ONAYLI, "x": ONAYLI,
    "bekliyor": BEKLIYOR, "onay-bekliyor": BEKLIYOR, "onay bekliyor": BEKLIYOR,
    "onay-beklemede": BEKLIYOR, "beklemede": BEKLIYOR, "pending": BEKLIYOR,
    "open": BEKLIYOR, "taslak": BEKLIYOR, "sırada": BEKLIYOR, "sirada": BEKLIYOR,
    "koşuldu": KOSULDU, "kosuldu": KOSULDU, "koşuldu.": KOSULDU, "çalıştırıldı": KOSULDU,
    "calistirildi": KOSULDU, "ran": KOSULDU,
    "atlandı": ATLANDI, "atlandi": ATLANDI, "skipped": ATLANDI, "iptal": ATLANDI,
    "reddedildi": ATLANDI, "rejected": ATLANDI,
    "sahipsiz": SAHIPSIZ, "atanmamış": SAHIPSIZ, "atanmamis": SAHIPSIZ,
    "ownerless": SAHIPSIZ, "unassigned": SAHIPSIZ,
}


def _durum_normallestir(ham: Optional[str], kutu: Optional[str] = None) -> str:
    """Ham durum sözcüğünü sözlükten geçirir; bilinmeyeni olduğu gibi (küçük harf) döner."""
    if ham:
        d = ham.strip().strip("`*_").lower()
        return _DURUM_ESANLAMLILARI.get(d, d)
    if kutu is not None and kutu.lower() == "x":
        return ONAYLI
    return BEKLIYOR


def _tablo_hucreleri(satir: str) -> Optional[List[Dict[str, Any]]]:
    """``| a | b |`` satırını hücre konumlarıyla çözer. Tablo değilse/ayraçsa ``None``."""
    m = _TABLO_SATIRI.match(str(satir or ""))
    if not m:
        return None
    ic = m.group(1)
    hucreler = [
        {"ham": hm.group(0), "bas": hm.start(), "son": hm.end()}
        for hm in re.finditer(r"[^|]+", ic)
    ]
    if not hucreler:
        return None
    if all(_TABLO_AYRAC_HUCRE.match(h["ham"].strip()) or not h["ham"].strip() for h in hucreler):
        return None  # |---|---| ayraç satırı
    return hucreler


def _tablo_kalemi(satir: str, no: int) -> Optional[Dict[str, Any]]:
    """Tablo satırını kaleme çevirir; başlık/ayraç/boş satırda ``None``."""
    hucreler = _tablo_hucreleri(satir)
    if not hucreler:
        return None
    temiz = [h["ham"].strip().strip("`*_") for h in hucreler]
    dolu = [t for t in temiz if t]
    if not dolu:
        return None
    if all(t.lower() in _TABLO_BASLIKLARI for t in dolu):
        return None  # başlık satırı
    kid = next((t for t in temiz if _TABLO_ID.match(t)), "")
    if not kid or len(hucreler) < 4:
        # Kuyruk kalemi tablosu: id hücresi AÇIK olmalı ve satır en az 4 hücreli.
        # Böylece dosyadaki ölçüm/karar tabloları (tarih, "—", düz metin) kalem sayılmaz.
        return None
    durum = next(
        (_DURUM_ESANLAMLILARI[t.lower()] for t in temiz if t.lower() in _DURUM_ESANLAMLILARI),
        BEKLIYOR,
    )
    efor = next((t for t in temiz if _TABLO_EFOR.match(t)), "")
    return {
        "id": kid.strip("`"),
        "durum": durum,
        "efor": efor,
        "satir_no": no,
        "metin": str(satir).strip(),
    }


def _kalem_ayristir_satir(satir: str, no: int) -> Optional[Dict[str, Any]]:
    """Tek satırı kaleme çevirir (önce tablo, sonra madde işareti biçimi)."""
    tablo = _tablo_kalemi(satir, no)
    if tablo:
        return tablo
    m = _SATIR_KALEMI.match(str(satir or ""))
    if not m:
        return None
    govde = m.group(1).strip()
    kutu: Optional[str] = None
    km = _KUTU_ISARETI.match(govde)
    if km:
        kutu = km.group(1)
        govde = km.group(2).strip()
    im = _ID_ALANI.search(govde)
    if im:
        kid = im.group(1).strip()
    elif kutu is not None:
        # Yalnız AÇIK kutu işaretli satırlarda ilk kelime id sayılır (`- [ ] K-001 …`).
        ilk = re.split(r"[\s|·;,]+", govde)[0] if govde else ""
        kid = ilk.strip().strip("`*_")
    else:
        return None  # gövde metni kalem sayılmaz: ya `id:` alanı ya kutu gerekir
    if not kid:
        return None
    dm = _DURUM_ALANI.search(govde)
    em = _EFOR_ALANI.search(govde)
    return {
        "id": kid,
        "durum": _durum_normallestir(dm.group(1) if dm else None, kutu),
        "efor": em.group(1).strip() if em else "",
        "satir_no": no,
        "metin": govde,
    }


def kuyruk_ayristir(metin: str) -> List[Dict[str, Any]]:
    """Kuyruk markdown'ını kalem listesine çevirir.

    İki biçim desteklenir:
      * tablo satırı     : ``| K-001 | iş | sahip | kanıt | onay-bekliyor | pencere |``
      * madde işareti    : ``- …``, ``* …``, ``+ …``, ``1. …`` ya da ``1) …``
    Madde biçiminde alanlar ``anahtar: değer`` (veya ``anahtar=değer``); ``|`` ve ``·`` ayraçtır.
    Başlık (``| ID | … | DURUM | … |``) ve ayraç (``|---|---|``) satırları atlanır.
    """
    kalemler: List[Dict[str, Any]] = []
    for i, satir in enumerate(str(metin or "").splitlines(), start=1):
        kalem = _kalem_ayristir_satir(satir, i)
        if kalem:
            kalemler.append(kalem)
    return kalemler


def kuyruk_sayilari(kalemler: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    """``{"bekleyen": n, "onaylı": n, "toplam": n, …}``.

    ``bekleyen`` geriye uyumluluk için "onaysız" anlamındadır; ``beklemede`` yalnız
    durumu ``bekliyor`` olanları sayar, diğer durumlar kendi adlarıyla gelir.
    """
    kalem_listesi = list(kalemler or [])
    sayim = {ONAYLI: 0, BEKLIYOR: 0, KOSULDU: 0, ATLANDI: 0, SAHIPSIZ: 0}
    for k in kalem_listesi:
        d = str(k.get("durum"))
        sayim[d] = sayim.get(d, 0) + 1
    onayli = sayim[ONAYLI]
    return {
        "bekleyen": len(kalem_listesi) - onayli,
        "onaylı": onayli,
        "beklemede": sayim[BEKLIYOR],
        "koşuldu": sayim[KOSULDU],
        "atlandı": sayim[ATLANDI],
        "sahipsiz": sayim[SAHIPSIZ],
        "toplam": len(kalem_listesi),
    }


def id_listesi_coz(ham: str) -> List[str]:
    """``"a, b c"`` → ``["a", "b", "c"]`` (sıra korunur, tekrarlar atılır)."""
    parcalar = [p.strip() for p in re.split(r"[,\s]+", str(ham or "")) if p.strip()]
    gorulen: List[str] = []
    for p in parcalar:
        if p not in gorulen:
            gorulen.append(p)
    return gorulen


def kuyruk_onayla(metin: str, idler: Sequence[str]) -> Tuple[str, List[str]]:
    """Verilen id'leri ``onaylı`` yapar; (yeni metin, değişen id listesi) döner.

    Yalnız ilgili kalem satırının durumu/kutusu değişir, satırın kalanı bayt bayt korunur.
    """
    hedef = {str(i) for i in (idler or [])}
    degisen: List[str] = []
    if not hedef:
        return str(metin or ""), degisen
    satirlar = str(metin or "").splitlines(keepends=True)
    for idx, satir in enumerate(satirlar):
        yalin = satir.rstrip("\r\n")
        son = satir[len(yalin):]
        # ── tablo satırı: yalnız durum hücresi değişir, satırın kalanı korunur ──
        tablo_m = _TABLO_SATIRI.match(yalin)
        hucreler = _tablo_hucreleri(yalin) if tablo_m else None
        if hucreler:
            temiz = [h["ham"].strip().strip("`*_") for h in hucreler]
            dolu = [t for t in temiz if t]
            if not dolu or all(t.lower() in _TABLO_BASLIKLARI for t in dolu):
                continue  # başlık ya da boş satır
            kid = next((t for t in temiz if _TABLO_ID.match(t)), "")
            kid = kid.strip("`")
            if not kid or len(hucreler) < 4 or kid not in hedef:
                continue
            durum_idx = next(
                (i for i, t in enumerate(temiz) if t.lower() in _DURUM_ESANLAMLILARI), None
            )
            if durum_idx is not None and _DURUM_ESANLAMLILARI[temiz[durum_idx].lower()] == ONAYLI:
                continue  # zaten onaylı
            if durum_idx is None:
                durum_idx = next((i for i, h in enumerate(hucreler) if not h["ham"].strip()), None)
            if durum_idx is not None:
                hucre = hucreler[durum_idx]
                bosluk_bas = hucre["ham"][: len(hucre["ham"]) - len(hucre["ham"].lstrip())]
                bosluk_son = hucre["ham"][len(hucre["ham"].rstrip()):]
                yeni_hucre = (bosluk_bas or " ") + ONAYLI + (bosluk_son or " ")
                govde_bas = tablo_m.start(1) + hucre["bas"]
                govde_son = tablo_m.start(1) + hucre["son"]
                yeni_yalin = yalin[:govde_bas] + yeni_hucre + yalin[govde_son:]
            else:
                # durum kolonu yok: son hücreden önce yeni bir hücre ekle
                yeni_yalin = yalin.rstrip()[:-1].rstrip() + " | " + ONAYLI + " |"
            satirlar[idx] = yeni_yalin + son
            degisen.append(kid)
            continue
        m = _SATIR_KALEMI.match(yalin)
        if not m:
            continue
        onizleme, govde = yalin[: m.start(1)], m.group(1)
        km = _KUTU_ISARETI.match(govde.strip())
        govde_temiz = govde.strip()
        kutu = ""
        if km:
            kutu, govde_temiz = km.group(1), km.group(2).strip()
        im = _ID_ALANI.search(govde_temiz)
        kid = im.group(1).strip() if im else (re.split(r"[\s|·;,]+", govde_temiz)[0] if govde_temiz else "")
        if kid not in hedef:
            continue
        dm = _DURUM_ALANI.search(govde_temiz)
        if dm and _durum_normallestir(dm.group(1)) == ONAYLI:
            continue  # zaten onaylı (alan)
        if kutu is not None and kutu.lower() == "x":
            continue  # zaten onaylı (kutu)
        yeni_govde = govde_temiz
        if dm:
            yeni_govde = govde_temiz[: dm.start(1)] + ONAYLI + govde_temiz[dm.end(1):]
        elif kutu:
            yeni_govde = "[x] " + govde_temiz
        else:
            yeni_govde = govde_temiz + " · durum: " + ONAYLI
        satirlar[idx] = onizleme + (" " if govde[:1].isspace() else "") + yeni_govde + son
        degisen.append(kid)
    return "".join(satirlar), degisen


# ── Ayarlar (saf birleştirme) ─────────────────────────────────────────
def _bool(deger: Any) -> bool:
    if isinstance(deger, bool):
        return deger
    return str(deger).strip().lower() in {"1", "true", "yes", "evet", "on", "açık", "acik"}


def _sayi(deger: Any, varsayilan: Any) -> Any:
    try:
        return type(varsayilan)(deger) if not isinstance(varsayilan, bool) else varsayilan
    except (TypeError, ValueError):
        try:
            f = float(deger)
            return int(f) if isinstance(varsayilan, int) else f
        except (TypeError, ValueError):
            return varsayilan


def ayarlari_birlestir(ham: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Bilinmeyen anahtarları yok sayar, tipleri varsayılana göre zorlar."""
    ayar = dict(VARSAYILAN_AYARLAR)
    if not isinstance(ham, dict):
        return ayar
    for anahtar, varsayilan in VARSAYILAN_AYARLAR.items():
        if anahtar not in ham or ham[anahtar] is None:
            continue
        if isinstance(varsayilan, bool):
            ayar[anahtar] = _bool(ham[anahtar])
        elif isinstance(varsayilan, (int, float)):
            ayar[anahtar] = _sayi(ham[anahtar], varsayilan)
        else:
            ayar[anahtar] = str(ham[anahtar])
    return ayar


def yol_genislet(yol: str) -> str:
    """``~`` genişletme (saf olmayan tek yardımcı; ağ/dosya erişimi yok)."""
    import os

    return os.path.expanduser(str(yol or ""))
