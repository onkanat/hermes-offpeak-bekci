"""offpeak-bekci — opt-in kurulum planı (saf çekirdek, W4b).

Neden ayrı modül: `/offpeak-kur` ve `/offpeak-kaldir` komutlarının ürettiği *plan* burada
tek yerde durur; komut yalnız planı basar ve onay alır. Modül bilerek saftır — saat, ağ,
dosya yazımı yok; girdi (ayarlar + bulunan yollar) parametre olarak girer, çıktı aynı girdi
için bayt bayt aynıdır. Bu yüzden plan/hash/kaldırma kararları gerçek kurulum olmadan
sınanabilir (bkz. ``tests/test_kurulum.py``).

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

#: İşi tanıyan işaret: prompt'un içinde durur, ``/offpeak-kaldir`` işi bununla bulur.
ISARET = "[offpeak-bekci:kurulum]"

#: Kurulan işin adı (ASCII: cron/CLI/günlük satırlarında kodlama sorunu çıkmasın).
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

#: ``/offpeak-kur`` çıktısında planın nasıl onaylanacağı.
ONAY_ORNEK = "/offpeak-kur onayla <plan_hash> [duraklat]"

#: "Geri alma yolu" — komut çıktıları kullanıcıya bunu söyler.
GERI_ALMA = (
    "geri alma: kurudan sonra `hermes cron list` ile iş id'sini bul, "
    "`cronjob_manage action='remove' job_id=<id>` (ya da `/offpeak-kaldir onayla <id>`)"
)

#: Prompt gövdesi. ``{kuyruk}`` yer tutucusu düz ``replace`` ile doldurulur (``str.format``
#: gömülü süslü parantezlerde kırılır — bkz. test_parite'teki 16.10.2026 dersi).
_PROMPT = """OFF-PEAK KUYRUK KOŞUCUSU — kurulum işareti: ISARET_BUYUK
Kuyruk defteri: {kuyruk}
Kuyruk şeması: tablo satırı `| ID | iş | sahip | kanıt ölçütü | durum | pencere |` ya da
madde satırı (`- id: K-001 · durum: onay-bekliyor · …`). Satır sonundaki monitör eki:
`· ONAYLI=<n> · KOSULMAMIŞ=<m>`.

KURALLAR
1. Yalnız `durum` alanı `onaylı` olan kalemleri koş. `onay-bekliyor`/`sahipsiz` kalemlere
   DOKUNMA: onaysız kalem hiçbir pencerede koşmaz. Onay YALNIZ kullanıcı verir
   (`/offpeak-onayla <id,id>`); sen `durum` alanını `koşuldu` dışında hiçbir değere çevirme.
2. Her kalem: işi yap → çıktı dosyasını/kanıtı üret → kuyrukta o kalemi `koşuldu` yap ve
   kanıtı (EXIT kodu / dosya yolu / sayı) işle. Bitiremediğin kalemi `koşuldu` yapma, nedenini yaz.
3. MONİTÖR SATIRI → EYLEM (satır TAM 1 satırdır; bağlamdaki `MONITOR CHANGE DETECTED` diff'i
   önceki tike göre neyin değiştiğini gösterir):
   3a. `OFFPEAK_BASLADI … x0.5` → pencere off-peak: kural 1'e göre `onaylı` kalemleri koş;
       koşulacak kalem yoksa hiçbir şey koşma, 1 satır durum yaz.
   3b. `PEAK_BASLADI … x1.0` → pencere peak: hiçbir kalemi koşma; 1 satır durum yaz
       (`PEAK penceresi: kalem koşulmadı · ONAYLI=<n> · KOSULMAMIŞ=<m>`).
   3c. `DEGISIKLIK_YOK · ONAYLI=<n> · KOSULMAMIŞ=<m>` + diff'te ONAYLI/KOSULMAMIŞ değişmiş →
       pencere geçişi değil KUYRUK DEĞİŞİMİDİR (yeni onay ya da yeni kalem): pencereyi
       monitör betiğinin `--durum` (salt sorgu) çıktısıyla doğrula; çıktı off-peak ise kural 1'i
       uygula, peak ise hiçbir kalemi koşma, 1 satır bildir ve bitir.
   3d. `DEGISIKLIK_YOK` + diff'te kuyruk alanları değişmemiş → hiçbir şey koşma, kuyruk
       dosyasına yazma; 1 satır `değişiklik yok` yaz ve bitir.
4. Kuyruk dosyası yok/bozuksa hiçbir kalemi koşma; nedeni yaz.
5. Bu makinenin config.yaml'ını değiştirme, başka makineye/profile dokunma, yeni cron işi kurma.
6. Sonunda en fazla 10 satır özet: koşulan kalem(ler), kanıt yolları, kalan onaylı/bekleyen
   sayısı, engel. Bu işaret satırını (ISARET_BUYUK) silme — `/offpeak-kaldir` işi bununla bulur."""


def _prompt_uret(kuyruk: str) -> str:
    """Runner prompt'u: kuyruk yolu + işaret + kurallar (düz ``replace`` ile)."""
    return (
        _PROMPT.replace("ISARET_BUYUK", ISARET)
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

    ``ayar``: ``bekci_core`` etkin ayarları. ``monitor_var``: monitör betiği profilin
    ``scripts/`` dizininde bulundu mu (kurulumu yapan katman ölçer, plan yalnız karar verir).
    Monitör yoksa plan pencere açılışına zamanlanır ve gerekçesi ``uyarilar``da bildirilir —
    monitörsüz bir işi 5 dakikada bir uyandırmak her tikte ajan koşumudur (maliyet tuzağı).
    """
    zamanlama = POLL_ZAMANLAMA if monitor_var else str(ayar.get("schedule") or "").strip()
    monitor = VARSAYILAN_MONITOR if monitor_var else ""
    uyarilar: List[str] = []
    if not monitor_var:
        uyarilar.append(
            "monitör betiği bulunamadı ({}): iş yalnız pencere açılışında koşar; "
            "hafta sonu ve gündüz off-peak pencereleri kapsanmaz.".format(VARSAYILAN_MONITOR)
        )
    if not kuyruk_var:
        uyarilar.append(
            "kuyruk defteri yok ({}): iş kurulsa da koşacak kalem bulunamaz; "
            "önce defteri oluştur.".format(kuyruk_yolu)
        )
    if not workdir_var or not workdir:
        uyarilar.append("çalışma dizini yok: iş workdir'siz kurulur (profil evinden koşar).")
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
        "prompt": _prompt_uret(kuyruk_yolu),
        "isaret": ISARET,
        "monitor_var": bool(monitor_var),
        "kuyruk_var": bool(kuyruk_var),
        "uyarilar": uyarilar,
    }
    return plan


def kurulacak_alanlar(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Onaya konu olan alanlar (kurulacak işi birebir tanımlayanlar).

    ``uyarilar``/``monitor_var`` gibi *türev* alanlar hash'e girmez: hash, kurulacak işin
    kendisini temsil etsin diye yalnız kurulum parametreleri üzerinden hesaplanır.
    """
    alanlar = ("is_adi", "zamanlama", "monitor", "workdir", "enabled_toolsets", "teslim", "prompt")
    return {alan: plan.get(alan) for alan in alanlar}


def plan_hash(plan: Dict[str, Any]) -> str:
    """Planın kısa parmak izi (ilk 8 hex): onay bu hash'e bağlanır."""
    ham = json.dumps(kurulacak_alanlar(plan), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(ham.encode("utf-8")).hexdigest()[:8]


def cronjob_parametreleri(plan: Dict[str, Any], *, paused: bool = False) -> Dict[str, Any]:
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
        parametreler["paused_reason"] = "offpeak-bekci prova: /offpeak-kur ile kuruldu, hemen kaldırılır"
    return parametreler


def parametre_json(parametreler: Dict[str, Any]) -> str:
    """Parametrelerin tek satır JSON'u (onay çıktısında ve oturuma bırakılan mesajda)."""
    return json.dumps(parametreler, ensure_ascii=False, sort_keys=False)


def kurulum_bildirimi(plan: Dict[str, Any], *, paused: bool = False) -> str:
    """``/offpeak-kur`` çıktısı: kurulacak işi TAM gösterir, hiçbir şey yaratmaz."""
    p = cronjob_parametreleri(plan, paused=paused)
    satirlar = [
        "offpeak-bekci — KURULACAK İŞ (henüz hiçbir şey kurulmadı)",
        f"  iş adı        : {plan['is_adi']}",
        f"  zamanlama     : {plan['zamanlama']}"
        + ("   (monitör kapılı poll: çıktı değişmezse ajan KOŞMAZ, 0 token)"
           if plan["varyant"] == VARYANT_BEKCI else ""),
        f"  monitör       : {plan['monitor'] or '(yok)'}"
        + (f" ({plan['monitor_yolu']})" if plan["monitor"] and plan.get("monitor_yolu") else ""),
        f"  çalışma dizini: {plan['workdir'] or '(yok — profil evi)'}",
        f"  araç kümeleri : {', '.join(plan['enabled_toolsets']) or '(yok)'}",
        f"  teslim        : {plan['teslim']} (bildirim yok; kayıt cron geçmişinde)",
        f"  kuyruk defteri: {plan['kuyruk']}",
        f"  varyant       : {plan['varyant']}",
        "",
        "PROMPT (işin ajanına verilecek metnin tamamı):",
        "---8<---",
        plan["prompt"],
        "--->8---",
        "",
        f"plan_hash: {plan_hash(plan)}",
    ]
    if plan.get("uyarilar"):
        satirlar.append("UYARILAR:")
        satirlar.extend(f"  - {u}" for u in plan["uyarilar"])
    ozet = plan_hash(plan)
    satirlar += [
        "",
        f"onayla (kur)  : /offpeak-kur onayla {ozet}",
        f"prova         : /offpeak-kur onayla {ozet} duraklat   [duraklatılmış kurulur]",
        "kurulumu EKLENTİ yapmaz: onaydan sonra işi ajanın kendi cron aracı kurar; "
        "eklenti jobs.json'a yazmaz.",
        GERI_ALMA,
    ]
    return "\n".join(satirlar)


def enjeksiyon_metni(
    plan: Dict[str, Any], parametreler: Dict[str, Any], *, paused: bool = False
) -> str:
    """Kullanıcı onayından sonra oturuma bırakılan mesaj (ajan cron işini bununla kurar)."""
    return "\n".join([
        f"[offpeak-bekci] Kullanıcı `/offpeak-kur onayla {plan_hash(plan)}` onayını verdi"
        + (" (duraklatılmış kurulum)" if paused else "") + ".",
        "Bu mesajı offpeak-bekci eklentisi üretti; içerik kullanıcı onaylı plandır.",
        "YAPILACAK: aşağıdaki cron işini `cronjob_manage` aracıyla KUR (parametreleri değiştirme):",
        parametre_json(parametreler),
        "Kurduktan sonra TEK satır bildir: iş id'si + `hermes cron list` satırı"
        + (" ve işin duraklatılmış olduğu" if paused else "") + ".",
        f"Plan {plan_hash(plan)} · kuyruk defteri: {plan['kuyruk']}",
        GERI_ALMA,
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


def kurulu_listesi(bulunan: Sequence[Dict[str, Any]]) -> str:
    """``/offpeak-kaldir`` (argümansız) çıktısı: kurulu işleri gösterir, hiçbir şey kaldırmaz."""
    if not bulunan:
        return (
            "kurulu offpeak işi bulunamadı (profil cron deposu okundu).\n"
            f"kur: `{ONAY_ORNEK.split(' [')[0]}`"
        )
    satirlar = ["offpeak-bekci — KURULU İŞLER (henüz hiçbir şey kaldırılmadı)"]
    for is_ in bulunan:
        im = "eklenti işi" if is_["isaretli"] else "işaretsiz (elle kurulmuş olabilir)"
        satirlar.append(
            f"  {is_['id']} · {is_['name']} · {is_['schedule_display']} · "
            f"{'etkin' if is_['enabled'] else 'duraklatılmış'} · durum={is_['state'] or '?'} · {im}"
        )
        satirlar.append(
            f"      sonraki koşu: {is_['next_run_at'] or '-'} · monitör: {is_['monitor'] or '-'} · "
            f"workdir: {is_['workdir'] or '-'}"
        )
    satirlar += [
        "",
        "kaldır (onayla): /offpeak-kaldir onayla <job_id>",
        "kaldırmayı EKLENTİ yapmaz: onaydan sonra işi ajanın kendi cron aracı kaldırır.",
        "geri alma: /offpeak-kur ile yeniden kur (plan aynıysa aynı plan_hash).",
    ]
    return "\n".join(satirlar)


def kaldirma_parametreleri(job_id: str) -> Dict[str, Any]:
    """``cronjob_manage`` kaldırma parametreleri (işi AJAN kaldırır; eklenti yazmaz)."""
    return {"action": "remove", "job_id": str(job_id)}


def kaldirma_enjeksiyon_metni(is_: Dict[str, Any]) -> str:
    """Onaylanan kaldırma için oturuma bırakılan mesaj."""
    return "\n".join([
        f"[offpeak-bekci] Kullanıcı `/offpeak-kaldir onayla {is_['id']}` onayını verdi.",
        "Bu mesajı offpeak-bekci eklentisi üretti; içerik kullanıcı onaylı plandır.",
        f"KALDIRILACAK İŞ: {is_['id']} · {is_['name']} · {is_['schedule_display']} · "
        f"{'etkin' if is_['enabled'] else 'duraklatılmış'}",
        "YAPILACAK: aşağıdaki cron işini `cronjob_manage` aracıyla KALDIR:",
        parametre_json(kaldirma_parametreleri(is_["id"])),
        f"Kaldırdıktan sonra TEK satır bildir: iş id'si + `hermes cron list` içinde artık "
        f"görünmediği.",
        "geri alma: /offpeak-kur ile yeniden kur.",
    ])


def kaldirma_bildirimi(is_: Dict[str, Any]) -> str:
    """Onaylı kaldırmanın komut çıktısı (kaldırma parametreleri + geri alma yolu)."""
    return "\n".join([
        f"offpeak-bekci — KALDIRMA ONAYI: {is_['id']} · {is_['name']}",
        f"  zamanlama: {is_['schedule_display']} · durum: {is_['state'] or '?'} · "
        f"{'etkin' if is_['enabled'] else 'duraklatılmış'}",
        "  parametreler: " + parametre_json(kaldirma_parametreleri(is_["id"])),
        "geri alma: /offpeak-kur ile yeniden kur.",
    ])
