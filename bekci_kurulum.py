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
    zamanlama = POLL_ZAMANLAMA if monitor_var else str(ayar.get("schedule") or "").strip()
    monitor = VARSAYILAN_MONITOR if monitor_var else ""
    uyarilar: List[str] = []
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
