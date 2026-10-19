"""`yerel_kron` — UTC pencere beyanının yerel saat karşılığı (19.10.2026 hatası).

Ölçülmüş hata: Hermes'in cron zamanlayıcısı ifadeyi YEREL saatle yorumlar
(`0 8 * * 1` → Next run 08:00 +03). Plan `5 18 * * 1-5` ifadesini "18:05 UTC" diye
belgeliyordu; birebir kurulunca iş 18:05 yerel = 15:05 UTC'de, yani peak penceresinin
(12:00–18:00 UTC) İÇİNDE koştu. Bu testler çevirinin kendisini kilitler.
"""

from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

import bekci_kurulum as k  # noqa: E402

UTC = dt.timezone.utc


class YerelKronTest(unittest.TestCase):
    def test_tr_18_05_utc_21_05_yerel(self) -> None:
        """TR (UTC+3, DST yok): 18:05 UTC → 21:05 yerel — sahada elle kurulan ifade."""
        r = k.yerel_kron("5 18 * * 1-5", tz="Europe/Istanbul",
                         simdi=dt.datetime(2026, 10, 19, 10, 0, tzinfo=UTC))
        self.assertEqual(r["ifade"], "5 21 * * 1-5")
        self.assertEqual(r["utc"], "5 18 * * 1-5")
        self.assertEqual(r["tz"], "Europe/Istanbul")
        self.assertEqual(r["gun_kaymasi"], 0)
        self.assertEqual(r["not"], "")

    def test_tr_yaz_kiş_ayni(self) -> None:
        """Türkiye 2016'dan beri kalıcı UTC+3: yaz da kış da 21:05."""
        yaz = k.yerel_kron("5 18 * * 1-5", tz="Europe/Istanbul",
                           simdi=dt.datetime(2026, 7, 15, 10, 0, tzinfo=UTC))
        kis = k.yerel_kron("5 18 * * 1-5", tz="Europe/Istanbul",
                           simdi=dt.datetime(2026, 1, 15, 10, 0, tzinfo=UTC))
        self.assertEqual(yaz["ifade"], "5 21 * * 1-5")
        self.assertEqual(kis["ifade"], "5 21 * * 1-5")

    def test_dst_bolgesi_mevsimle_kayar_ve_uyarir(self) -> None:
        """Berlin: kış 19:05, yaz 20:05 + 'DST geçişinde kayar' uyarısı."""
        kis = k.yerel_kron("5 18 * * 1-5", tz="Europe/Berlin",
                           simdi=dt.datetime(2026, 1, 15, 10, 0, tzinfo=UTC))
        yaz = k.yerel_kron("5 18 * * 1-5", tz="Europe/Berlin",
                           simdi=dt.datetime(2026, 7, 15, 10, 0, tzinfo=UTC))
        self.assertEqual(kis["ifade"], "5 19 * * 1-5")
        self.assertEqual(yaz["ifade"], "5 20 * * 1-5")
        self.assertIn("yaz saati", kis["not"])
        self.assertIn("yaz saati", yaz["not"])

    def test_gun_kaymasi_hafta_gununu_de_kaydirir(self) -> None:
        """23:30 UTC → 02:30 (ertesi gün) TR: hafta içi 1-5 → 2-6."""
        r = k.yerel_kron("30 23 * * 1-5", tz="Europe/Istanbul",
                         simdi=dt.datetime(2026, 10, 19, 10, 0, tzinfo=UTC))
        self.assertEqual(r["ifade"], "30 2 * * 2-6")
        self.assertEqual(r["gun_kaymasi"], 1)

    def test_pazar_gunu_kaymasi(self) -> None:
        """Cumartesi 23:30 UTC → Pazar 02:30 TR: 6 → 0 (cron'da 0 = Pazar)."""
        r = k.yerel_kron("30 23 * * 6", tz="Europe/Istanbul",
                         simdi=dt.datetime(2026, 10, 19, 10, 0, tzinfo=UTC))
        self.assertEqual(r["ifade"], "30 2 * * 0")

    def test_her_gun_ifadesi_korunur(self) -> None:
        r = k.yerel_kron("5 18 * * *", tz="Europe/Istanbul",
                         simdi=dt.datetime(2026, 10, 19, 10, 0, tzinfo=UTC))
        self.assertEqual(r["ifade"], "5 21 * * *")

    def test_poll_ifadesi_degismez_ve_uyari_uretmez(self) -> None:
        """`*/5 * * * *` dakika düzeyinde: saat diliminden bağımsız, aynen kalır."""
        r = k.yerel_kron(k.POLL_ZAMANLAMA, tz="Europe/Istanbul")
        self.assertEqual(r["ifade"], k.POLL_ZAMANLAMA)
        self.assertEqual(r["not"], "")

    def test_cozulemeyen_ifade_aynen_doner_ve_neden_soyler(self) -> None:
        """Sessizce yanlış ifade üretmek yok: çözülemeyen girdi aynen döner + not."""
        ornekler = {
            "5 18 * *": "5 alanlı değil",
            "0 0 * * MON": "hafta-günü",
            "*/5 18 * * 1-5": "sayısal değil",
            "5 99 * * 1-5": "aralık dışı",
        }
        for ifade, beklenen in ornekler.items():
            with self.subTest(ifade=ifade):
                r = k.yerel_kron(ifade, tz="Europe/Istanbul")
                self.assertEqual(r["ifade"], ifade)
                self.assertIn(beklenen, r["not"])


class PlanYerelTest(unittest.TestCase):
    """Plan, kurulacak ifadeyi YEREL üretir ve UTC beyanını ayrı taşır."""

    def _plan(self, monitor_var: bool) -> dict:
        return k.kurulum_plani({"schedule": "5 18 * * 1-5", "dil": "tr"},
                               kuyruk_yolu="~/k.md", monitor_var=monitor_var)

    def test_pencere_acilis_varyanti_yerel_saatte(self) -> None:
        plan = self._plan(monitor_var=False)
        self.assertEqual(plan["varyant"], k.VARYANT_ACILIS)
        self.assertEqual(plan["zamanlama_utc"], "5 18 * * 1-5")
        self.assertTrue(plan["saat_dilimi"], "saat dilimi adı planda görünmeli")
        # Yerel ifade UTC beyanından farklı olmalı (TR'de 21:05); eşitse çeviri yapılmamıştır.
        self.assertNotEqual(plan["zamanlama"], plan["zamanlama_utc"])

    def test_monitor_varyanti_poll_kalir(self) -> None:
        plan = self._plan(monitor_var=True)
        self.assertEqual(plan["varyant"], k.VARYANT_BEKCI)
        self.assertEqual(plan["zamanlama"], k.POLL_ZAMANLAMA)

    def test_plan_ciktisi_iki_saati_de_gosterir(self) -> None:
        plan = self._plan(monitor_var=False)
        metin = k.kurulum_bildirimi(plan)
        self.assertIn("5 18 * * 1-5", metin)   # pencere (UTC)
        self.assertIn(plan["zamanlama"], metin)  # kurulacak yerel ifade


if __name__ == "__main__":
    unittest.main()
