"""offpeak-bekci — kullanıcıya görünen metinlerin kataloğu (saf modül).

Neden ayrı modül: kullanıcının gördüğü her metin (komut açıklamaları, komut çıktıları,
rapor/uyarı metinleri) tek yerde durur; **İngilizce varsayılandır**, Türkçe `dil: tr`
ayarıyla seçilir (beyan: ``plugin.yaml`` → ``config_schema.dil``). Böylece arayüz dilini
değiştirmek kodun hiçbir yerine dokunmaz — yeni bir metin eklerken anahtar açılır, iki dil
karşılığı yazılır.

SINIRLAR: modül saftır — G/Ç yok, ağ yok, saat yok, global durum yok. Girdi (``dil`` kodu),
çıktı aynı girdi için bayt bayt aynıdır. ``{alan}`` yer tutucuları ``t()`` içinde ``format``
ile doldurulur; bu yüzden metinlerde gömülü süslü parantez bulunmaz (uzun ``prompt`` metni
bilerek ``replace`` ile doldurulur — bkz. ``bekci_kurulum._prompt_uret``).

Anahtar düzeni (``<yüzey>.<bölüm>``):
  * ``komut.*``     — komut açıklamaları ve ``args_hint`` (kayıt sırasında gösterilir)
  * ``rapor.*``     — ``/offpeak-durum`` insan okur raporu ve ``ozet`` alanı
  * ``onayla.*``    — ``/offpeak-onayla`` çıktısı
  * ``kur.*``       — ``/offpeak-kur`` çıktısı
  * ``kaldir.*``    — ``/offpeak-kaldir`` çıktısı
  * ``kuyruk.*``    — kuyruk defteri okuma hataları (``kuyruk_hata`` alanı)
  * ``kurulum.*``   — ``bekci_kurulum`` plan/liste/enjeksiyon metinleri
  * ``kayit.*``     — yerel günlüğe (JSONL) yazılan kullanıcı okur uyarı notu

Türkçe karşılıklar 17.10.2026'daki (0.1.3) yayımlanmış metinlerin BİREBİR aynısıdır: `dil: tr`
seçen kullanıcı sürprizle karşılaşmaz. İngilizce metinler aynı olguları söyler; alan adları,
sayılar ve makine sözleşmeleri (``/offpeak-durum json`` anahtarları, kuyruk durum değerleri
``onaylı``/``koşuldu``…, cron/POSIX alanları) DEĞİŞMEZ.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

#: Varsayılan arayüz dili (``plugin.yaml`` → ``config_schema.dil.default`` ile aynı).
VARSAYILAN_DIL = "en"

#: Kabul edilen dil kodları; başka bir değer → :data:`VARSAYILAN_DIL`.
DILLER = ("en", "tr")

#: ``anahtar`` → ``{"en": ..., "tr": ...}``. Türkçesi 0.1.3 metinlerinin birebir kopyasıdır.
METINLER: Dict[str, Dict[str, str]] = {
    # ── Komut beyanları (register_command) ─────────────────────────────────────────
    "komut.durum.aciklama": {
        "en": "Ollama off-peak window, countdown, quota and queue state (readable report; "
              "`json` gives the machine output).",
        "tr": "Ollama off-peak penceresi, geri sayım, kota ve kuyruk durumu (okunur rapor; "
              "`json` ile makine çıktısı).",
    },
    "komut.durum.ipucu": {"en": "[json]", "tr": "[json]"},
    "komut.onayla.aciklama": {
        "en": "Approves work items in the off-peak queue (only the user approves).",
        "tr": "Off-peak kuyruğundaki iş kalemlerini onaylı yapar (kullanıcı onayı).",
    },
    "komut.onayla.ipucu": {"en": "<id,id>", "tr": "<id,id>"},
    "komut.kur.aciklama": {
        "en": "Prints the plan of the opt-in off-peak cron job; `onayla <plan_hash> [duraklat]` "
              "leaves the install request to the session (the agent's cron tool installs it).",
        "tr": "Opt-in off-peak cron işinin planını gösterir; `onayla <plan_hash> [duraklat]` ile "
              "kurulum isteğini oturuma bırakır (işi ajanın cron aracı kurar).",
    },
    "komut.kur.ipucu": {"en": "[onayla <plan_hash> [duraklat]]", "tr": "[onayla <plan_hash> [duraklat]]"},
    "komut.kaldir.aciklama": {
        "en": "Lists installed offpeak cron jobs; `onayla <job_id>` leaves the removal request "
              "to the session (the agent's cron tool removes it).",
        "tr": "Kurulu offpeak cron işlerini listeler; `onayla <job_id>` ile kaldırma isteğini "
              "oturuma bırakır (işi ajanın cron aracı kaldırır).",
    },
    "komut.kaldir.ipucu": {"en": "[onayla <job_id>]", "tr": "[onayla <job_id>]"},

    # ── ozet alanı (JSON sözleşmesi: anahtar ve tip aynı; yalnız cümle dili değişir) ──
    "rapor.ozet": {
        "en": "{pencere} · {gelecek} in {geri_sayim} · queue {toplam} items · {onayli} approved · "
              "{kosuldu} done",
        "tr": "{pencere} · {gelecek} {geri_sayim} sonra · kuyruk {toplam} kalem · {onayli} onaylı · "
              "{kosuldu} koşuldu",
    },
    "rapor.ozet.ek": {
        "en": " · {n} awaiting approval or unclaimed",
        "tr": " · {n} onay/sahipsiz bekliyor",
    },

    # ── /offpeak-durum insan okur raporu ──────────────────────────────────────────
    "rapor.baslik": {
        "en": "**Off-peak watchdog** — {ozet}",
        "tr": "**Off-peak bekçisi** — {ozet}",
    },
    "rapor.pencere.temel": {
        "en": "- **window**: currently **{pencere}**",
        "tr": "- **pencere**: şu an **{pencere}**",
    },
    "rapor.pencere.aktif": {"en": " — off-peak ACTIVE", "tr": " — off-peak AKTİF"},
    "rapor.pencere.sonraki": {
        "en": " · next {gelecek} in **{geri_sayim}**",
        "tr": " · sonraki {gelecek} **{geri_sayim}** sonra",
    },
    "rapor.kuyruk": {
        "en": "- **queue**: {toplam} items · {onayli} approved · {kosuldu} done · {atlandi} skipped · "
              "{bekleyen} awaiting approval",
        "tr": "- **kuyruk**: {toplam} kalem · {onayli} onaylı · {kosuldu} koşuldu · {atlandi} atlandı · "
              "{bekleyen} onay bekliyor",
    },
    "rapor.kuyruk.sahipsiz": {"en": " · {n} unclaimed", "tr": " · {n} sahipsiz"},
    "rapor.kuru": {
        "en": "- **dry run**: {durum} · target rate: {hiz} calls/min · delay ceiling: {tavan} s",
        "tr": "- **kuru koşu**: {durum} · hedef hız: {hiz} çağrı/dk · erteleme tavanı: {tavan} sn",
    },
    "rapor.kuru.acik": {
        "en": "ON (measures only, never delays)",
        "tr": "AÇIK (yalnız ölçer, geciktirmez)",
    },
    "rapor.kuru.kapali": {
        "en": "OFF (can actually delay)",
        "tr": "KAPALI (gerçekten erteleyebilir)",
    },
    "rapor.son60": {
        "en": "- **last 60 s**: {sayi} LLM calls · quota: {kota}/{tavan} calls ({uyari})",
        "tr": "- **son 60 sn**: {sayi} LLM çağrısı · kota: {kota}/{tavan} çağrı ({uyari})",
    },
    "rapor.uyari.var": {"en": "WARNING", "tr": "UYARI VAR"},
    "rapor.uyari.yok": {"en": "no warning", "tr": "uyarı yok"},
    "rapor.bekleyenler": {
        "en": "- **awaiting approval/work**: {liste}",
        "tr": "- **onay/iş bekleyenler**: {liste}",
    },
    "rapor.bekleyenler.devam": {"en": "  … and {n} more", "tr": "  … ve {n} tane daha"},
    "rapor.bekleyen.yok": {
        "en": "- **awaiting approval**: none (all items done/skipped)",
        "tr": "- **onay bekleyen**: yok (tüm kalemler koşuldu/atlandı)",
    },
    "rapor.defter.ok": {"en": "- **queue ledger**: `{yol}` ✓", "tr": "- **kuyruk defteri**: `{yol}` ✓"},
    "rapor.defter.hata": {
        "en": "- **queue ledger**: `{yol}` ✗ UNREADABLE — {hata}",
        "tr": "- **kuyruk defteri**: `{yol}` ✗ OKUNAMADI — {hata}",
    },
    "rapor.makine": {
        "en": "_machine output (chip/automation): `/offpeak-durum json`_",
        "tr": "_makine çıktısı (rozet/otomasyon): `/offpeak-durum json`_",
    },

    # ── Kuyruk defteri okuma hataları (kuyruk_hata alanı) ──────────────────────────
    "kuyruk.hata.yok": {"en": "file missing: {yol}", "tr": "dosya yok: {yol}"},
    "kuyruk.hata.okunamadi": {"en": "could not be read: {hata}", "tr": "okunamadı: {hata}"},

    # ── /offpeak-onayla ────────────────────────────────────────────────────────────
    "onayla.kullanim": {
        "en": "usage: /offpeak-onayla <id,id>\nqueue: {yol}\nawaiting approval: {idler}",
        "tr": "kullanım: /offpeak-onayla <id,id>\nkuyruk: {yol}\nonay bekleyen: {idler}",
    },
    "onayla.bos": {"en": "(none)", "tr": "(yok)"},
    "onayla.dosya_yok": {
        "en": "queue file missing: {yol} — the plugin does not write its content, you create it.",
        "tr": "kuyruk dosyası yok: {yol} — içeriğini eklenti yazmaz, sen oluştur.",
    },
    "onayla.okunamadi": {
        "en": "queue could not be read: {yol} ({hata})",
        "tr": "kuyruk okunamadı: {yol} ({hata})",
    },
    "onayla.degisen_yok": {
        "en": "no item changed (already approved or not found): {idler}",
        "tr": "değişen kalem yok (zaten onaylı ya da bulunamadı): {idler}",
    },
    "onayla.yazilamadi": {
        "en": "queue could not be written: {yol} ({hata})",
        "tr": "kuyruk yazılamadı: {yol} ({hata})",
    },
    "onayla.basarili": {
        "en": "approved ({n}): {idler} · queue {bekleyen} waiting / {onayli} approved",
        "tr": "onaylandı ({n}): {idler} · kuyruk {bekleyen} bekliyor / {onayli} onaylı",
    },

    # ── /offpeak-kur ───────────────────────────────────────────────────────────────
    "kur.bilinmeyen": {
        "en": "unknown argument: {arg}\nusage: {ornek}\nshow the plan: /offpeak-kur",
        "tr": "bilinmeyen argüman: {arg}\nkullanım: {ornek}\nplanı göster: /offpeak-kur",
    },
    "kur.hash_kullanimi": {
        "en": "usage: {ornek}\nplan_hash: {ozet}\napproval requires the plan's own hash "
              "(prevents an accidental install).",
        "tr": "kullanım: {ornek}\nplan_hash: {ozet}\nonay planın kendi hash'ini ister "
              "(yanlışlıkla kurulumu önler).",
    },
    "kur.reddedildi": {
        "en": "APPROVAL REJECTED — the plan hash does not match, nothing was installed.\n"
              "  given      : {verilen}\n  plan_hash  : {ozet}\n"
              "the plan may have changed in the meantime (settings/queue path): look again with "
              "`/offpeak-kur`.",
        "tr": "ONAY REDDEDİLDİ — plan hash'i tutmuyor, hiçbir şey kurulmadı.\n"
              "  verilen    : {verilen}\n  plan_hash  : {ozet}\n"
              "plan bu arada değişmiş olabilir (ayar/kuyruk yolu): `/offpeak-kur` ile yeniden bak.",
    },
    "kur.onay_alindi": {
        "en": "APPROVAL RECEIVED (plan {ozet}{ek}) — the install request was left to the session; "
              "the agent's cron tool installs the job (the plugin does not write jobs.json).",
        "tr": "ONAY ALINDI (plan {ozet}{ek}) — kurulum isteği oturuma bırakıldı; işi ajanın cron "
              "aracı kurar (eklenti jobs.json'a yazmaz).",
    },
    "kur.onay_alindi_kanal_yok": {
        "en": "APPROVAL RECEIVED (plan {ozet}) — could not be left to the session in this channel; "
              "hand the parameter below to the agent or install it yourself with `cronjob_manage`.",
        "tr": "ONAY ALINDI (plan {ozet}) — bu kanalda oturuma bırakılamadı; aşağıdaki parametreyi "
              "ajana ver ya da `cronjob_manage` ile kendin kur.",
    },
    "kur.duraklat.ek": {"en": " · paused", "tr": " · duraklatılmış"},
    "kur.is_satiri": {
        "en": "job to install (single-line JSON): ",
        "tr": "kurulacak iş (tek satır JSON): ",
    },

    # ── /offpeak-kaldir ─────────────────────────────────────────────────────────────
    "kaldir.depo_hata": {
        "en": "{hata}\nnothing was removed (the plugin does not write the cron store).",
        "tr": "{hata}\nhiçbir şey kaldırılmadı (eklenti cron deposuna yazmaz).",
    },
    "kaldir.bilinmeyen": {
        "en": "unknown argument: {arg}\nusage: /offpeak-kaldir onayla <job_id> · to list: "
              "/offpeak-kaldir\n\n{liste}",
        "tr": "bilinmeyen argüman: {arg}\nkullanım: /offpeak-kaldir onayla <job_id> · liste için: "
              "/offpeak-kaldir\n\n{liste}",
    },
    "kaldir.kullanim": {
        "en": "usage: /offpeak-kaldir onayla <job_id>\n\n{liste}",
        "tr": "kullanım: /offpeak-kaldir onayla <job_id>\n\n{liste}",
    },
    "kaldir.farkli_is": {
        "en": "that id is not an offpeak job in this profile: {hedef} — nothing was removed.\n"
              "removal works only with an id from the list below.\n\n{liste}",
        "tr": "bu id bu profilde bir offpeak işi değil: {hedef} — hiçbir şey kaldırılmadı.\n"
              "kaldırma yalnız aşağıdaki listedeki id'lerle yapılır.\n\n{liste}",
    },
    "kaldir.onay": {
        "en": "REMOVAL APPROVED — the request was left to the session; the agent's cron tool "
              "removes the job.",
        "tr": "KALDIRMA ONAYI — istek oturuma bırakıldı; işi ajanın cron aracı kaldırır.",
    },
    "kaldir.onay_kanal_yok": {
        "en": "REMOVAL APPROVED — could not be left to the session in this channel; hand the "
              "parameter below to the agent.",
        "tr": "KALDIRMA ONAYI — bu kanalda oturuma bırakılamadı; aşağıdaki parametreyi ajana ver.",
    },
    "kaldir.cron.okunamadi": {
        "en": "cron store could not be read: {yol} ({hata})",
        "tr": "cron deposu okunamadı: {yol} ({hata})",
    },
    "kaldir.cron.bicim": {
        "en": "cron store has an unexpected shape: {yol}",
        "tr": "cron deposu beklenmeyen biçimde: {yol}",
    },

    # ── bekci_kurulum: plan (kurulum_bildirimi) ─────────────────────────────────────
    "kurulum.plan.baslik": {
        "en": "offpeak-bekci — JOB TO INSTALL (nothing has been installed yet)",
        "tr": "offpeak-bekci — KURULACAK İŞ (henüz hiçbir şey kurulmadı)",
    },
    "kurulum.plan.is_adi": {"en": "  job name        : {deger}", "tr": "  iş adı        : {deger}"},
    "kurulum.plan.zamanlama": {"en": "  schedule        : {deger}", "tr": "  zamanlama     : {deger}"},
    "kurulum.plan.monitor_kapili": {
        "en": "   (monitor-gated poll: the agent does NOT run unless the output changes, 0 tokens)",
        "tr": "   (monitör kapılı poll: çıktı değişmezse ajan KOŞMAZ, 0 token)",
    },
    "kurulum.plan.monitor": {"en": "  monitor         : {deger}", "tr": "  monitör       : {deger}"},
    "kurulum.plan.workdir": {"en": "  workdir         : {deger}", "tr": "  çalışma dizini: {deger}"},
    "kurulum.plan.araclar": {"en": "  toolsets        : {deger}", "tr": "  araç kümeleri : {deger}"},
    "kurulum.plan.teslim": {
        "en": "  delivery        : {teslim} (no notification; the record stays in cron history)",
        "tr": "  teslim        : {teslim} (bildirim yok; kayıt cron geçmişinde)",
    },
    "kurulum.plan.defter": {"en": "  queue ledger    : {deger}", "tr": "  kuyruk defteri: {deger}"},
    "kurulum.plan.varyant": {"en": "  variant         : {deger}", "tr": "  varyant       : {deger}"},
    "kurulum.plan.prompt_basligi": {
        "en": "PROMPT (the full text handed to the job's agent):",
        "tr": "PROMPT (işin ajanına verilecek metnin tamamı):",
    },
    "kurulum.plan.uyarilar": {"en": "WARNINGS:", "tr": "UYARILAR:"},
    "kurulum.plan.onay": {
        "en": "approve (install): /offpeak-kur onayla {ozet}",
        "tr": "onayla (kur)  : /offpeak-kur onayla {ozet}",
    },
    "kurulum.plan.prova": {
        "en": "dry run        : /offpeak-kur onayla {ozet} duraklat   [installed paused]",
        "tr": "prova         : /offpeak-kur onayla {ozet} duraklat   [duraklatılmış kurulur]",
    },
    "kurulum.plan.eklenti_yazmaz": {
        "en": "the PLUGIN does not install: after approval the agent's own cron tool installs the "
              "job; the plugin does not write jobs.json.",
        "tr": "kurulumu EKLENTİ yapmaz: onaydan sonra işi ajanın kendi cron aracı kurar; eklenti "
              "jobs.json'a yazmaz.",
    },
    "kurulum.deger_yok": {"en": "(none)", "tr": "(yok)"},
    "kurulum.workdir_yok": {"en": "(none — profile home)", "tr": "(yok — profil evi)"},

    # ── bekci_kurulum: uyarılar (plan["uyarilar"]) ──────────────────────────────────
    "kurulum.uyari.monitor_yok": {
        "en": "monitor script not found ({monitor}): the job only runs at the window opening; "
              "weekend and daytime off-peak windows are not covered.",
        "tr": "monitör betiği bulunamadı ({monitor}): iş yalnız pencere açılışında koşar; "
              "hafta sonu ve gündüz off-peak pencereleri kapsanmaz.",
    },
    "kurulum.uyari.kuyruk_yok": {
        "en": "queue ledger missing ({kuyruk}): even if the job is installed there is no item to "
              "run; create the ledger first.",
        "tr": "kuyruk defteri yok ({kuyruk}): iş kurulsa da koşacak kalem bulunamaz; "
              "önce defteri oluştur.",
    },
    "kurulum.uyari.workdir_yok": {
        "en": "workdir missing: the job is installed without a workdir (it runs from the profile "
              "home).",
        "tr": "çalışma dizini yok: iş workdir'siz kurulur (profil evinden koşar).",
    },

    # ── bekci_kurulum: kurulu işler listesi ─────────────────────────────────────────
    "kurulum.liste.bos": {
        "en": "no installed offpeak job found (the profile cron store was read).\ninstall: `{kur}`",
        "tr": "kurulu offpeak işi bulunamadı (profil cron deposu okundu).\nkur: `{kur}`",
    },
    "kurulum.liste.baslik": {
        "en": "offpeak-bekci — INSTALLED JOBS (nothing has been removed yet)",
        "tr": "offpeak-bekci — KURULU İŞLER (henüz hiçbir şey kaldırılmadı)",
    },
    "kurulum.liste.satir": {
        "en": "  {id} · {ad} · {zamanlama} · {durum} · state={state} · {im}",
        "tr": "  {id} · {ad} · {zamanlama} · {durum} · durum={state} · {im}",
    },
    "kurulum.liste.detay": {
        "en": "      next run: {zaman} · monitor: {monitor} · workdir: {workdir}",
        "tr": "      sonraki koşu: {zaman} · monitör: {monitor} · workdir: {workdir}",
    },
    "kurulum.liste.isaretli": {"en": "plugin job", "tr": "eklenti işi"},
    "kurulum.liste.isaretsiz": {
        "en": "unmarked (may have been installed by hand)",
        "tr": "işaretsiz (elle kurulmuş olabilir)",
    },
    "kurulum.liste.etkin": {"en": "enabled", "tr": "etkin"},
    "kurulum.liste.duraklatilmis": {"en": "paused", "tr": "duraklatılmış"},
    "kurulum.liste.kaldir": {
        "en": "remove (approve): /offpeak-kaldir onayla <job_id>",
        "tr": "kaldır (onayla): /offpeak-kaldir onayla <job_id>",
    },
    "kurulum.liste.eklenti_kaldirmaz": {
        "en": "the PLUGIN does not remove: after approval the agent's own cron tool removes the job.",
        "tr": "kaldırmayı EKLENTİ yapmaz: onaydan sonra işi ajanın kendi cron aracı kaldırır.",
    },
    "kurulum.liste.geri_alma": {
        "en": "undo: reinstall with /offpeak-kur (same plan_hash if the plan is unchanged).",
        "tr": "geri alma: /offpeak-kur ile yeniden kur (plan aynıysa aynı plan_hash).",
    },

    # ── bekci_kurulum: geri alma yolu (komut çıktılarında ortak) ────────────────────
    "kurulum.geri_alma": {
        "en": "undo: after the dry run find the job id with `hermes cron list`, "
              "`cronjob_manage action='remove' job_id=<id>` (or `/offpeak-kaldir onayla <id>`)",
        "tr": "geri alma: kurudan sonra `hermes cron list` ile iş id'sini bul, "
              "`cronjob_manage action='remove' job_id=<id>` (ya da `/offpeak-kaldir onayla <id>`)",
    },

    # ── bekci_kurulum: oturuma bırakılan enjeksiyon metinleri ───────────────────────
    "kurulum.enj.baslik": {
        "en": "[offpeak-bekci] The user approved `/offpeak-kur onayla {hash}`{ek}.",
        "tr": "[offpeak-bekci] Kullanıcı `/offpeak-kur onayla {hash}` onayını verdi{ek}.",
    },
    "kurulum.enj.duraklat.ek": {"en": " (paused install)", "tr": " (duraklatılmış kurulum)"},
    "kurulum.enj.ureten": {
        "en": "This message was produced by the offpeak-bekci plugin; the content is the "
              "user-approved plan.",
        "tr": "Bu mesajı offpeak-bekci eklentisi üretti; içerik kullanıcı onaylı plandır.",
    },
    "kurulum.enj.yapilacak": {
        "en": "TO DO: INSTALL the cron job below with the `cronjob_manage` tool (do not change the "
              "parameters):",
        "tr": "YAPILACAK: aşağıdaki cron işini `cronjob_manage` aracıyla KUR (parametreleri "
              "değiştirme):",
    },
    "kurulum.enj.bildir": {
        "en": "After installing, report in ONE line: the job id + the `hermes cron list` line{ek}.",
        "tr": "Kurduktan sonra TEK satır bildir: iş id'si + `hermes cron list` satırı{ek}.",
    },
    "kurulum.enj.bildir.duraklat.ek": {
        "en": " and that the job is paused",
        "tr": " ve işin duraklatılmış olduğu",
    },
    "kurulum.enj.plan": {
        "en": "Plan {hash} · queue ledger: {kuyruk}",
        "tr": "Plan {hash} · kuyruk defteri: {kuyruk}",
    },
    "kurulum.kaldir_enj.baslik": {
        "en": "[offpeak-bekci] The user approved `/offpeak-kaldir onayla {id}`.",
        "tr": "[offpeak-bekci] Kullanıcı `/offpeak-kaldir onayla {id}` onayını verdi.",
    },
    "kurulum.kaldir_enj.hedef": {
        "en": "JOB TO REMOVE: {id} · {ad} · {zamanlama} · {durum}",
        "tr": "KALDIRILACAK İŞ: {id} · {ad} · {zamanlama} · {durum}",
    },
    "kurulum.kaldir_enj.yapilacak": {
        "en": "TO DO: REMOVE the cron job below with the `cronjob_manage` tool:",
        "tr": "YAPILACAK: aşağıdaki cron işini `cronjob_manage` aracıyla KALDIR:",
    },
    "kurulum.kaldir_enj.bildir": {
        "en": "After removing, report in ONE line: the job id + that it no longer shows up in "
              "`hermes cron list`.",
        "tr": "Kaldırdıktan sonra TEK satır bildir: iş id'si + `hermes cron list` içinde artık "
              "görünmediği.",
    },
    "kurulum.kaldir_enj.geri_alma": {
        "en": "undo: reinstall with /offpeak-kur.",
        "tr": "geri alma: /offpeak-kur ile yeniden kur.",
    },

    # ── bekci_kurulum: onaylı kaldırmanın komut çıktısı ─────────────────────────────
    "kurulum.kaldirma.baslik": {
        "en": "offpeak-bekci — REMOVAL APPROVED: {id} · {ad}",
        "tr": "offpeak-bekci — KALDIRMA ONAYI: {id} · {ad}",
    },
    "kurulum.kaldirma.satir": {
        "en": "  schedule: {zamanlama} · state: {state} · {durum}",
        "tr": "  zamanlama: {zamanlama} · durum: {state} · {durum}",
    },
    "kurulum.kaldirma.parametreler": {"en": "  parameters: {json}", "tr": "  parametreler: {json}"},

    # ── bekci_kurulum: duraklatılmış kurulum gerekçesi (cronjob parametresi) ───────
    "kurulum.paused_reason": {
        "en": "offpeak-bekci dry run: installed via /offpeak-kur, removed right away",
        "tr": "offpeak-bekci prova: /offpeak-kur ile kuruldu, hemen kaldırılır",
    },

    # ── bekci_kurulum: prompt (işin ajanına verilen metin; replace ile doldurulur) ──
    "kurulum.prompt": {
        "en": """OFF-PEAK QUEUE RUNNER — install marker: ISARET_BUYUK
Queue ledger: {kuyruk}
Queue schema: table row `| ID | job | owner | evidence criterion | status | window |` or a
bullet line (`- id: K-001 · durum: onay-bekliyor · …`). Monitor suffix at the end of the row:
`· ONAYLI=<n> · KOSULMAMIŞ=<m>`.

RULES
1. Run only items whose `durum` field is `onaylı`. Do NOT touch `onay-bekliyor`/`sahipsiz`
   items: an unapproved item never runs in any window. Approval is given by the USER only
   (`/offpeak-onayla <id,id>`); never change the `durum` field to any value other than `koşuldu`.
2. For each item: do the work → produce the output file/evidence → set that item to `koşuldu`
   in the ledger and record the evidence (EXIT code / file path / number). Do not mark an item
   you could not finish as `koşuldu`; write the reason instead.
3. MONITOR LINE → ACTION (a monitor line is EXACTLY 1 line; the `MONITOR CHANGE DETECTED` diff in
   context shows what changed since the previous tick):
   3a. `OFFPEAK_BASLADI … x0.5` → the window is off-peak: run the `onaylı` items per rule 1;
       if there is nothing to run, run nothing and write 1 status line.
   3b. `PEAK_BASLADI … x1.0` → the window is peak: run no item; write 1 status line
       (`PEAK penceresi: kalem koşulmadı · ONAYLI=<n> · KOSULMAMIŞ=<m>`).
   3c. `DEGISIKLIK_YOK · ONAYLI=<n> · KOSULMAMIŞ=<m>` and the diff shows ONAYLI/KOSULMAMIŞ
       changed → this is not a window transition but a QUEUE CHANGE (a new approval or a new
       item): verify the window with the monitor script's `--durum` (read-only query) output;
       if the output is off-peak apply rule 1, if it is peak run no item, report 1 line and finish.
   3d. `DEGISIKLIK_YOK` and no queue field changed in the diff → run nothing, do not write to the
       ledger; write 1 line `değişiklik yok` and finish.
4. If the ledger is missing/corrupt run no item; write the reason.
5. Do not change this machine's config.yaml, do not touch another machine/profile, do not
   install a new cron job.
6. At the end at most 10 lines of summary: item(s) run, evidence paths, remaining
   approved/awaiting counts, blockers. Do not delete this marker line (ISARET_BUYUK) —
   `/offpeak-kaldir` finds the job with it.""",
        "tr": """OFF-PEAK KUYRUK KOŞUCUSU — kurulum işareti: ISARET_BUYUK
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
   sayısı, engel. Bu işaret satırını (ISARET_BUYUK) silme — `/offpeak-kaldir` işi bununla bulur.""",
    },

    # ── Yerel günlüğe (JSONL) yazılan kullanıcı okur uyarı notu ─────────────────────
    "kayit.kota_uyari.not": {
        "en": "the request was not cancelled; this is only an alert record",
        "tr": "istek iptal edilmedi; yalnız uyarı kaydı",
    },
    "kayit.kurulum_eklenti_degil": {
        "en": "the agent's cron tool installs the job",
        "tr": "işi ajanın cron aracı kurar",
    },
}


def _kod(ham: Any) -> str:
    """Ham değeri geçerli dil koduna indirger: ``"tr"``/``"en"``; başka her şey → ``"en"``."""
    kod = str(ham or "").strip().lower()
    return kod if kod in DILLER else VARSAYILAN_DIL


def dil_sec(ayar: Any = None) -> str:
    """Etkin ayarlardan ``dil`` değerini okur; yok/anlaşılmaz/eksik katman → varsayılan ``"en"``.

    ``ayar``: ``bekci_core`` etkin ayarları (``__init__._ayarlar``) — sözlük ya da dil kodu.
    Eski kurulumlarda ``dil`` anahtarı hiç bulunmaz: o hâlde İngilizce (varsayılan) geçerlidir.
    """
    ham = ayar.get("dil") if isinstance(ayar, Mapping) else ayar
    return _kod(ham)


def t(anahtar: str, dil: Any = VARSAYILAN_DIL, **kw: Any) -> str:
    """``anahtar`` metnini ``dil`` dilinde döndürür; ``kw`` verilirse ``{alan}``lar doldurulur.

    ``dil``: dil kodu (``"en"``/``"tr"``) ya da etkin ayar sözlüğü (``dil_sec`` uygulanır).
    Bilinmeyen anahtar ya da eksik dil karşılığı sessizce geçilmez: ``KeyError`` yükseltir
    (arayüz metni eksik kalırsa testte/doğrulamada görünsün).
    """
    kayit = METINLER.get(str(anahtar))
    if not kayit:
        raise KeyError(f"metinler: bilinmeyen anahtar: {anahtar}")
    kod = dil_sec(dil)
    metin = kayit.get(kod) or kayit.get(VARSAYILAN_DIL)
    if metin is None:  # pragma: no cover — katalog bozuksa
        raise KeyError(f"metinler: {anahtar} için {kod} metni yok")
    return metin.format(**kw) if kw else metin
