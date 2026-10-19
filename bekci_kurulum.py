"""offpeak-bekci — opt-in kurulum planı (saf çekirdek, W4b).

Neden ayrı modül: `/offpeak-kur` ve `/offpeak-kaldir` komutlarının ürettiği *plan* burada
tek yerde durur; komut yalnız planı basar ve onay alır. Modül bilerek saftır — saat, ağ,
dosya yazımı yok; girdi (ayarlar + bulunan yollar) parametre olarak girer, çıktı aynı girdi
için bayt bayt aynıdır. Bu yüzden plan/hash/kaldırma kararları gerçek kurulum olmadan
sınanabilir (bkz. ``tests/test_kurulum.py``).

DİL: kullanıcıya görünen her metin ``metinler`` kataloğundan gelir — **varsayılan İngilizce**,
``dil: tr`` ile Türkçe (``plugin.yaml`` → ``config_schema.dil``). Dil, plana giren etkin
ayarlardan okunur (``plan["dil"]``) ve gösterim fonksiyonlarına ``dil=`` parametresiyle de
verilebilir. Makine alanları (``varyant``, ``teslim``, ``is_adi``, ``plan_hash``, cron
parametreleri) dilden BAĞIMSIZDIR: dil değişince kurulum sözleşmesi değişmez, yalnız metin
değişir (prompt da dilden bağımsız değildir — işin ajanına verilen metindir).

SINIRLAR (şartname W4b):
  * Eklenti ``jobs.json``'a **YAZMAZ**. Plan yalnız ``cronjob_manage`` aracına verilecek
    parametreleri üretir; işi ajanın kendi cron aracı kurar (kullanıcı onayından sonra).
  * Onay, planın **içeriğine bağlıdır**: ``plan_hash`` kurulacak alanların kanonik JSON'unun
    sha256'sıdır. Gösterilen plan ile onaylanan plan ayrışırsa komut kurmaz.
  * Kullanıcıya özel hiçbir yol/değer bu modülde sabitlenmez: kuyruk yolu ve pencere beyanı
    ayarlardan (``plugin.yaml`` → ``config_schema`` + kurulumun ``config.yaml`` bloğu) gelir;
    monitör betiği adı görelidir ve cron motoru onu profilin ``scripts/`` dizininde çözer.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Sequence

try:  # eklenti paketi içinde (yükleyici + testler) çalışırken
    from . import metinler as _metin
except ImportError:  # pragma: no cover — dosya tek başına (üst düzey) import edilirse
    import metinler as _metin  # type: ignore[no-redef]

#: İşi tanıyan işaret: prompt'un içinde durur, ``/offpeak-kaldir`` işi bununla bulur.
ISARET = "[offpeak-bekci:kurulum]"

#: Kurulan işin adı (ASCII: cron/CLI/günlük satırlarında kodlama sorunu çıkmasın).
#: DİLE BAĞLI DEĞİLDİR: işin kimliğidir (kurulu işler bu adla bulunur/tanınır) — çevrilmez.
IS_ADI = "offpeak-kuyruk-kosusu (bekci kapili)"

#: Plan varyantları.
VARYANT_BEKCI = "bekci_kapili"  # monitör betiği var → 0-token tik + pencere geçişinde uyanış
VARYANT_ACILIS = "pencere_acilis"  # monitör yok → yalnız beyan edilen pencere açılışında koşar

#: Monitör betiği adı (göreli): cron motoru bunu profilin ``scripts/`` dizininde çözer.
VARSAYILAN_MONITOR = "offpeak_bekci.py"

#: Monitörlü varyantta tik aralığı: her 5 dk bir "ucuz" kontrol; çıktı değişmezse ajan KOŞMAZ
#: (0 token). Pencere geçişi ya da kuyruk değişimi çıktıyı değiştirir → ajan uyanır.
#: Yalnız pencere açılışına zamanlanan iş hafta sonu ve gündüz off-peak pencerelerini kaçırırdı.
POLL_ZAMANLAMA = "*/5 * * * *"

#: İşin ajanına verilecek araç kümeleri (kuyruk defteri + kanıt dosyaları + skill).
VARSAYILAN_TOOLSETLER: Sequence[str] = ("file", "terminal", "skills")


def _gun_alani(alan: str) -> Optional[List[int]]:
    """Cron hafta-günü alanını kümeye çevirir (0/7 = Pazar). Çözülemezse ``None``."""
    alan = alan.strip()
    if alan in {"*", "?"}:
        return list(range(7))
    kume: set[int] = set()
    for parca in alan.split(","):
        parca = parca.strip()
        if not parca:
            return None
        if "-" in parca:
            a, _, b = parca.partition("-")
            try:
                a_i, b_i = int(a), int(b)
            except ValueError:
                return None
            if b_i < a_i:
                return None
            kume.update(range(a_i, b_i + 1))
        else:
            try:
                kume.add(int(parca))
            except ValueError:
                return None
    if any(g < 0 or g > 7 for g in kume):
        return None
    return sorted({g % 7 for g in kume})


def _gun_metni(gunler: Sequence[int]) -> str:
    """Gün kümesini kompakt cron metnine çevirir (``2-6``, ``1,3``, ``*``)."""
    kume = sorted({g % 7 for g in gunler})
    if len(kume) == 7:
        return "*"
    parcalar: List[str] = []
    i = 0
    while i < len(kume):
        j = i
        while j + 1 < len(kume) and kume[j + 1] == kume[j] + 1:
            j += 1
        if j - i >= 2:
            parcalar.append(f"{kume[i]}-{kume[j]}")
        else:
            parcalar.extend(str(g) for g in kume[i:j + 1])
        i = j + 1
    return ",".join(parcalar)


def _sistem_bolge():
    """Sistem saat dilimini adlı ``ZoneInfo`` olarak döndürür (DST'yi doğru çözmek için).

    ``datetime.now().astimezone().tzinfo`` sabit ofset verir; yaz saati geçişinde kaymayı
    göremez. Sıra: ``TZ`` ortam değişkeni → ``/etc/localtime`` bağlantısı → sabit ofset (son çare).
    """
    import datetime as _dt
    import os
    import pathlib

    from zoneinfo import ZoneInfo

    ad = os.environ.get("TZ", "").strip().lstrip(":")
    if ad:
        try:
            return ZoneInfo(ad)
        except Exception:  # noqa: BLE001
            pass
    try:
        hedef = pathlib.Path("/etc/localtime").resolve()
        parcalar = hedef.parts
        if "zoneinfo" in parcalar:
            anahtar = "/".join(parcalar[parcalar.index("zoneinfo") + 1:])
            return ZoneInfo(anahtar)
    except Exception:  # noqa: BLE001
        pass
    return _dt.datetime.now().astimezone().tzinfo


def yerel_kron(
    utc_ifade: str,
    *,
    tz: Optional[str] = None,
    simdi: Optional[Any] = None,
) -> Dict[str, Any]:
    """UTC hedefli 5 alanlı cron ifadesini **yerel saat** ifadesine çevirir.

    Neden (ölçülmüş hata, 19.10.2026, saha kurulumu): Hermes'in cron zamanlayıcısı ifadeyi **yerel**
    saatle yorumlar (`0 8 * * 1` → Next run 08:00 +03). Planın varsayılanı `5 18 * * 1-5`
    "18:05 UTC" diye belgelenmişti; birebir kurulunca iş 18:05 **yerel** = 15:05 UTC'de, yani
    peak penceresinin (12:00–18:00 UTC) İÇİNDE koşuyordu — eklentinin amacına aykırı.

    Çeviri, hedef UTC anının **bir sonraki gerçekleşmesindeki** yerel karşılığını alır (yaz saati
    dahil). Gün sınırı aşılırsa hafta-günü alanı da kaydırılır. Çözülemeyen ifade **aynıen** döner
    ve ``not`` nedeni söyler: sessizce yanlış ifade üretmek, hiç çevirmemekten kötüdür.
    """
    import datetime as _dt

    alanlar = str(utc_ifade or "").split()
    sonuc: Dict[str, Any] = {"ifade": str(utc_ifade or "").strip(), "utc": str(utc_ifade or "").strip(),
                             "tz": "", "gun_kaymasi": 0, "not": ""}
    if len(alanlar) != 5:
        sonuc["not"] = "ifade 5 alanlı değil; yerel karşılık hesaplanmadı"
        return sonuc
    try:
        dk, saat = int(alanlar[0]), int(alanlar[1])
    except ValueError:
        # Saat alanı `*`/`*/n` ise ifade her saat başı koşar; yerel/UTC ayrımı pencereyi
        # kaydırmaz → çeviri gerekmez, uyarı da gerekmez. Dakika alanı `*/n` olsa bile saat
        # alanı sayısalsa çeviri şarttır (aşağıdaki uyarı doğru kalır).
        if alanlar[1] == "*" or alanlar[1].startswith("*/"):
            sonuc["not"] = ""
            return sonuc
        sonuc["not"] = "dk/saat alanı sayısal değil (ad/aralık); yerel karşılık hesaplanmadı"
        return sonuc
    if not (0 <= dk <= 59 and 0 <= saat <= 23):
        sonuc["not"] = "dk/saat aralık dışı; yerel karşılık hesaplanmadı"
        return sonuc
    gunler = _gun_alani(alanlar[4])
    if gunler is None:
        sonuc["not"] = "hafta-günü alanı çözülemedi; yerel karşılık hesaplanmadı"
        return sonuc

    try:
        from zoneinfo import ZoneInfo

        bolge = _sistem_bolge() if not tz else ZoneInfo(tz)
        yerel_ad = bolge
        simdi_utc = (simdi or _dt.datetime.now(_dt.timezone.utc))
        if simdi_utc.tzinfo is None:
            simdi_utc = simdi_utc.replace(tzinfo=_dt.timezone.utc)
        simdi_utc = simdi_utc.astimezone(_dt.timezone.utc)

        aday = simdi_utc.replace(hour=saat, minute=dk, second=0, microsecond=0)
        if aday <= simdi_utc:
            aday += _dt.timedelta(days=1)
        for _ in range(8):
            if ((aday.weekday() + 1) % 7) in gunler:  # cron: 0=Pazar, Python: 0=Pazartesi
                break
            aday += _dt.timedelta(days=1)
        yerel = aday.astimezone(bolge)  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001 — saat dilimi çözülemezse plan kurulmaz, uyarı verir
        sonuc["not"] = f"saat dilimi çözülemedi ({type(exc).__name__}); yerel karşılık hesaplanmadı"
        return sonuc

    kayma = (yerel.date() - aday.date()).days
    yeni_gunler = [(g + kayma) % 7 for g in gunler]
    sonuc.update({
        "ifade": f"{yerel.minute} {yerel.hour} * * {_gun_metni(yeni_gunler)}",
        "tz": str(getattr(yerel_ad, "key", yerel_ad)),
        "gun_kaymasi": kayma,
    })
    try:
        yaz = aday.replace(month=((aday.month + 5) % 12) + 1)
        if yaz.astimezone(bolge).utcoffset() != aday.astimezone(bolge).utcoffset():  # type: ignore[arg-type]
            sonuc["not"] = ("yaz saati bölgesi: ifade bugünkü ofsete göre; DST geçişinde ±1 saat "
                            "kayar — geçişten sonra `/offpeak-kur` planını yeniden koş")
    except Exception:  # noqa: BLE001 — yalnız uyarı; çeviri geçerli
        pass
    return sonuc

#: Sonuç teslimi: yerel (bildirim yok; koşum kaydı cron geçmişinde kalır).
VARSAYILAN_TESLIM = "local"

#: ``/offpeak-kur`` çıktısında planın nasıl onaylanacağı. DİLE BAĞLI DEĞİLDİR: komut söz
#: dizimidir; ``onayla``/``duraklat`` argüman adları her dilde aynı yazılır (ayrıştırıcı).
ONAY_ORNEK = "/offpeak-kur onayla <plan_hash> [duraklat]"

#: Geri alma metni artık katalogdadır (``metinler`` → ``kurulum.geri_alma``); bu sabit geriye
#: dönük okunabilirlik için durur ve katalogdaki Türkçe metnin aynısıdır.
GERI_ALMA = _metin.t("kurulum.geri_alma", "tr")


def _dil(plan: Dict[str, Any], dil: Optional[str] = None) -> str:
    """Metinlerin dili: açıkça verilen ``dil``, yoksa planın kendi dili, yoksa İngilizce."""
    return _metin.dil_sec(dil if dil is not None else plan.get("dil"))


def _prompt_uret(kuyruk: str, dil: str = _metin.VARSAYILAN_DIL) -> str:
    """Runner prompt'u: kuyruk yolu + işaret + kurallar (düz ``replace`` ile).

    ``str.format`` KULLANILMAZ: prompt gövdesinde gömülü ``{}`` olsaydı ``KeyError`` verirdi
    (bkz. 16.10.2026 kaydı). Bu yüzden ``metinler.t`` yer tutucusuz çağrılır, doldurma
    ``replace`` ile yapılır.
    """
    return (
        _metin.t("kurulum.prompt", dil)
        .replace("ISARET_BUYUK", ISARET)
        .replace("{kuyruk}", str(kuyruk))
    )


def kurulum_plani(
    ayar: Dict[str, Any],
    *,
    kuyruk_yolu: str,
    monitor_yolu: Optional[str] = None,
    monitor_var: bool = False,
    kuyruk_var: bool = True,
    workdir: Optional[str] = None,
    workdir_var: bool = True,
) -> Dict[str, Any]:
    """Kurulacak işin tam planı (saf: dosya/saat okumaz).

    ``ayar``: ``bekci_core`` etkin ayarları (dil buradan gelir). ``monitor_var``: monitör betiği
    profilin ``scripts/`` dizininde bulundu mu (kurulumu yapan katman ölçer, plan yalnız karar
    verir). Monitör yoksa plan pencere açılışına zamanlanır ve gerekçesi ``uyarilar``da
    bildirilir — monitörsüz bir işi 5 dakikada bir uyandırmak her tikte ajan koşumudur
    (maliyet tuzağı).
    """
    dil = _metin.dil_sec(ayar)
    # Hermes'in cron zamanlayıcısı ifadeyi YEREL saatle yorumlar (ölçüldü, 19.10.2026:
    # `0 8 * * 1` → Next run 08:00 +03). Bu yüzden pencere beyanı (UTC) kurulacak ifadeye
    # çevrilir; monitörsüz varyantta iş pencere AÇILIŞINDA (yerel karşılığıyla) koşar.
    ham_ifade = POLL_ZAMANLAMA if monitor_var else str(ayar.get("schedule") or "").strip()
    cevrim = yerel_kron(ham_ifade)
    zamanlama = cevrim["ifade"]
    monitor = VARSAYILAN_MONITOR if monitor_var else ""
    uyarilar: List[str] = []
    if cevrim["not"] and cevrim["ifade"] != ham_ifade:
        uyarilar.append(cevrim["not"])
    if not monitor_var:
        uyarilar.append(_metin.t("kurulum.uyari.monitor_yok", dil, monitor=VARSAYILAN_MONITOR))
    if not kuyruk_var:
        uyarilar.append(_metin.t("kurulum.uyari.kuyruk_yok", dil, kuyruk=kuyruk_yolu))
    if not workdir_var or not workdir:
        uyarilar.append(_metin.t("kurulum.uyari.workdir_yok", dil))
    plan: Dict[str, Any] = {
        "varyant": VARYANT_BEKCI if monitor_var else VARYANT_ACILIS,
        "is_adi": IS_ADI,
        "zamanlama": zamanlama,
        #: Pencere beyanı (UTC) — göstermelik değil: yerel ifadenin kaynağıdır ve denetimde kullanılır.
        "zamanlama_utc": ham_ifade,
        "saat_dilimi": str(cevrim["tz"] or ""),
        "pencere_beyani": str(ayar.get("schedule") or ""),
        "monitor": monitor,
        "monitor_yolu": str(monitor_yolu or ""),
        "workdir": str(workdir) if (workdir_var and workdir) else "",
        "enabled_toolsets": list(VARSAYILAN_TOOLSETLER),
        "teslim": VARSAYILAN_TESLIM,
        "kuyruk": str(kuyruk_yolu),
        "prompt": _prompt_uret(kuyruk_yolu, dil),
        "isaret": ISARET,
        "monitor_var": bool(monitor_var),
        "kuyruk_var": bool(kuyruk_var),
        "uyarilar": uyarilar,
        # Yalnız gösterim dilidir; kurulacak alanların (ve plan_hash'in) parçası DEĞİLDİR.
        "dil": dil,
    }
    return plan


def kurulacak_alanlar(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Onaya konu olan alanlar (kurulacak işi birebir tanımlayanlar).

    ``uyarilar``/``monitor_var`` gibi *türev* alanlar hash'e girmez: hash, kurulacak işin
    kendisini temsil etsin diye yalnız kurulum parametreleri üzerinden hesaplanır. ``dil`` de
    türevdir (gösterim); ama prompt dile bağlı olduğu için dolaylı olarak hash'e yansır.
    """
    alanlar = ("is_adi", "zamanlama", "monitor", "workdir", "enabled_toolsets", "teslim", "prompt")
    return {alan: plan.get(alan) for alan in alanlar}


def plan_hash(plan: Dict[str, Any]) -> str:
    """Planın kısa parmak izi (ilk 8 hex): onay bu hash'e bağlanır."""
    ham = json.dumps(kurulacak_alanlar(plan), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(ham.encode("utf-8")).hexdigest()[:8]


def cronjob_parametreleri(
    plan: Dict[str, Any], *, paused: bool = False, dil: Optional[str] = None
) -> Dict[str, Any]:
    """``cronjob_manage`` aracına verilecek parametreler (işi AJAN kurar; eklenti yazmaz)."""
    parametreler: Dict[str, Any] = {
        "action": "create",
        "name": plan["is_adi"],
        "schedule": plan["zamanlama"],
        "prompt": plan["prompt"],
        "enabled_toolsets": list(plan.get("enabled_toolsets") or []),
        "deliver": plan["teslim"],
    }
    if plan.get("monitor"):
        parametreler["monitor"] = plan["monitor"]
    if plan.get("workdir"):
        parametreler["workdir"] = plan["workdir"]
    if paused:
        parametreler["paused"] = True
        parametreler["paused_reason"] = _metin.t("kurulum.paused_reason", _dil(plan, dil))
    return parametreler


def parametre_json(parametreler: Dict[str, Any]) -> str:
    """Parametrelerin tek satır JSON'u (onay çıktısında ve oturuma bırakılan mesajda)."""
    return json.dumps(parametreler, ensure_ascii=False, sort_keys=False)


def kurulum_bildirimi(
    plan: Dict[str, Any], *, paused: bool = False, dil: Optional[str] = None
) -> str:
    """``/offpeak-kur`` çıktısı: kurulacak işi TAM gösterir, hiçbir şey yaratmaz."""
    dil = _dil(plan, dil)
    p = cronjob_parametreleri(plan, paused=paused, dil=dil)
    yok = _metin.t("kurulum.deger_yok", dil)
    satirlar = [
        _metin.t("kurulum.plan.baslik", dil),
        _metin.t("kurulum.plan.is_adi", dil, deger=plan["is_adi"]),
        _metin.t("kurulum.plan.zamanlama", dil, deger=plan["zamanlama"])
        + (_metin.t("kurulum.plan.monitor_kapili", dil)
           if plan["varyant"] == VARYANT_BEKCI else ""),
        _metin.t("kurulum.plan.zamanlama_utc", dil, deger=plan.get("zamanlama_utc") or yok),
        _metin.t("kurulum.plan.saat_dilimi", dil, deger=plan.get("saat_dilimi") or yok),
        _metin.t("kurulum.plan.monitor", dil, deger=plan["monitor"] or yok)
        + (f" ({plan['monitor_yolu']})" if plan["monitor"] and plan.get("monitor_yolu") else ""),
        _metin.t("kurulum.plan.workdir", dil,
                 deger=plan["workdir"] or _metin.t("kurulum.workdir_yok", dil)),
        _metin.t("kurulum.plan.araclar", dil, deger=", ".join(plan["enabled_toolsets"]) or yok),
        _metin.t("kurulum.plan.teslim", dil, teslim=plan["teslim"]),
        _metin.t("kurulum.plan.defter", dil, deger=plan["kuyruk"]),
        _metin.t("kurulum.plan.varyant", dil, deger=plan["varyant"]),
        "",
        _metin.t("kurulum.plan.prompt_basligi", dil),
        "---8<---",
        plan["prompt"],
        "--->8---",
        "",
        f"plan_hash: {plan_hash(plan)}",
    ]
    if plan.get("uyarilar"):
        satirlar.append(_metin.t("kurulum.plan.uyarilar", dil))
        satirlar.extend(f"  - {u}" for u in plan["uyarilar"])
    ozet = plan_hash(plan)
    satirlar += [
        "",
        _metin.t("kurulum.plan.onay", dil, ozet=ozet),
        _metin.t("kurulum.plan.prova", dil, ozet=ozet),
        _metin.t("kurulum.plan.eklenti_yazmaz", dil),
        _metin.t("kurulum.geri_alma", dil),
    ]
    return "\n".join(satirlar)


def enjeksiyon_metni(
    plan: Dict[str, Any], parametreler: Dict[str, Any], *, paused: bool = False,
    dil: Optional[str] = None,
) -> str:
    """Kullanıcı onayından sonra oturuma bırakılan mesaj (ajan cron işini bununla kurar)."""
    dil = _dil(plan, dil)
    return "\n".join([
        _metin.t("kurulum.enj.baslik", dil, hash=plan_hash(plan),
                 ek=_metin.t("kurulum.enj.duraklat.ek", dil) if paused else ""),
        _metin.t("kurulum.enj.ureten", dil),
        _metin.t("kurulum.enj.yapilacak", dil),
        parametre_json(parametreler),
        _metin.t("kurulum.enj.bildir", dil,
                 ek=_metin.t("kurulum.enj.bildir.duraklat.ek", dil) if paused else ""),
        _metin.t("kurulum.enj.plan", dil, hash=plan_hash(plan), kuyruk=plan["kuyruk"]),
        _metin.t("kurulum.geri_alma", dil),
    ])


def is_isareti_metni(metin: str) -> bool:
    """Metin eklentinin kurulum işaretini taşıyor mu?"""
    return ISARET in str(metin or "")


def _zamanlama_goster(is_: Dict[str, Any]) -> str:
    """İşin zamanlamasını tek satırda gösterir (``schedule_display`` ya da ``schedule`` sözlüğü)."""
    goster = is_.get("schedule_display")
    if isinstance(goster, str) and goster.strip():
        return goster.strip()
    z = is_.get("schedule")
    if isinstance(z, dict):
        return str(z.get("display") or z.get("expr") or z.get("kind") or "")
    return str(z or "")


def kurulu_isleri_bul(isler: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Kurulu cron işlerinden offpeak işlerini süzer (saf).

    İki sınıf döner: ``isaretli`` (bu eklentinin kurduğu işler — prompt'ta işaret var) ve
    ``eski`` (elle kurulmuş olabilecek emsaller: ad/prompt'ta offpeak geçer). Kaldırma yalnız
    AÇIK job id + onayla yapılır; komut işaretli olmayanı da kaldırabilir ama listede işaretler.
    """
    bulunan: List[Dict[str, Any]] = []
    for is_ in isler or []:
        if not isinstance(is_, dict):
            continue
        is_ = dict(is_)
        ad = str(is_.get("name") or "")
        prompt = str(is_.get("prompt") or "")
        isaretli = is_isareti_metni(prompt)
        eski = (not isaretli) and ("offpeak" in ad.lower() or "off-peak" in (ad + prompt).lower())
        if not (isaretli or eski):
            continue
        bulunan.append({
            "id": str(is_.get("id") or ""),
            "name": ad,
            "schedule_display": _zamanlama_goster(is_),
            "enabled": bool(is_.get("enabled")),
            "state": str(is_.get("state") or ""),
            "next_run_at": is_.get("next_run_at"),
            "last_run_at": is_.get("last_run_at"),
            "monitor": is_.get("monitor_script") or "",
            "workdir": is_.get("workdir") or "",
            "isaretli": isaretli,
        })
    return bulunan


def kurulu_listesi(bulunan: Sequence[Dict[str, Any]], *, dil: Optional[str] = None) -> str:
    """``/offpeak-kaldir`` (argümansız) çıktısı: kurulu işleri gösterir, hiçbir şey kaldırmaz."""
    dil = _metin.dil_sec(dil)
    if not bulunan:
        return "\n".join([
            _metin.t("kurulum.liste.bos", dil, kur=ONAY_ORNEK.split(" [")[0]),
        ])
    satirlar = [_metin.t("kurulum.liste.baslik", dil)]
    for is_ in bulunan:
        im = _metin.t("kurulum.liste.isaretli" if is_["isaretli"] else "kurulum.liste.isaretsiz", dil)
        durum = _metin.t("kurulum.liste.etkin" if is_["enabled"] else "kurulum.liste.duraklatilmis", dil)
        satirlar.append(_metin.t(
            "kurulum.liste.satir", dil,
            id=is_["id"], ad=is_["name"], zamanlama=is_["schedule_display"],
            durum=durum, state=is_["state"] or "?", im=im,
        ))
        satirlar.append(_metin.t(
            "kurulum.liste.detay", dil,
            zaman=is_["next_run_at"] or "-", monitor=is_["monitor"] or "-",
            workdir=is_["workdir"] or "-",
        ))
    satirlar += [
        "",
        _metin.t("kurulum.liste.kaldir", dil),
        _metin.t("kurulum.liste.eklenti_kaldirmaz", dil),
        _metin.t("kurulum.liste.geri_alma", dil),
    ]
    return "\n".join(satirlar)


def kaldirma_parametreleri(job_id: str) -> Dict[str, Any]:
    """``cronjob_manage`` kaldırma parametreleri (işi AJAN kaldırır; eklenti yazmaz)."""
    return {"action": "remove", "job_id": str(job_id)}


def kaldirma_enjeksiyon_metni(is_: Dict[str, Any], *, dil: Optional[str] = None) -> str:
    """Onaylanan kaldırma için oturuma bırakılan mesaj."""
    dil = _metin.dil_sec(dil)
    return "\n".join([
        _metin.t("kurulum.kaldir_enj.baslik", dil, id=is_["id"]),
        _metin.t("kurulum.enj.ureten", dil),
        _metin.t("kurulum.kaldir_enj.hedef", dil, id=is_["id"], ad=is_["name"],
                 zamanlama=is_["schedule_display"],
                 durum=_metin.t("kurulum.liste.etkin" if is_["enabled"]
                                else "kurulum.liste.duraklatilmis", dil)),
        _metin.t("kurulum.kaldir_enj.yapilacak", dil),
        parametre_json(kaldirma_parametreleri(is_["id"])),
        _metin.t("kurulum.kaldir_enj.bildir", dil),
        _metin.t("kurulum.kaldir_enj.geri_alma", dil),
    ])


def kaldirma_bildirimi(is_: Dict[str, Any], *, dil: Optional[str] = None) -> str:
    """Onaylı kaldırmanın komut çıktısı (kaldırma parametreleri + geri alma yolu)."""
    dil = _metin.dil_sec(dil)
    return "\n".join([
        _metin.t("kurulum.kaldirma.baslik", dil, id=is_["id"], ad=is_["name"]),
        _metin.t("kurulum.kaldirma.satir", dil, zamanlama=is_["schedule_display"],
                 state=is_["state"] or "?",
                 durum=_metin.t("kurulum.liste.etkin" if is_["enabled"]
                                else "kurulum.liste.duraklatilmis", dil)),
        _metin.t("kurulum.kaldirma.parametreler", dil, json=parametre_json(kaldirma_parametreleri(is_["id"]))),
        _metin.t("kurulum.kaldir_enj.geri_alma", dil),
    ])
