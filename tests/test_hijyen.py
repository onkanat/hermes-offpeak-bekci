#!/usr/bin/env python3
"""Yayın hijyeni KAPISI — kamuya açık ağaçta iç altyapı izi ya da sır kalmasın.

Neden var: 16.10.2026'da kamuya açık depoda (9480afb) gerçek bir LAN adresi (192.168.1.9) ve bir
makine adı (delinux01) bulundu; elle tarama yetmiyor çünkü her yeni commit kapıyı yeniden açar.
Bu test ağacı tarar ve ihlali satır satır söyler. Ağ/sır gerektirmez, deterministik, hızlıdır.

İZİN VERİLENLER (sızıntı değil):
  - Kodun KENDİ yerel-aralık listesi (`_YEREL_ISARETLERI`: "192.168.", "10.0." gibi ÖNEKLER) — tam IP değil.
  - Testlerdeki GENEL/örnek adresler: 10.0.0.1 · 10.0.0.2 · RFC 5737 (192.0.2.x) — hiçbir makineyi göstermez.
  - Yazar/kimlik bilgisi (LICENSE, plugin.yaml) ve kamuya açık depo adresleri.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import unittest

KOK = pathlib.Path(__file__).resolve().parents[1]

#: Tam IPv4 (önek değil) → sonra özel aralık mı diye süzülür: 192.168.x.x · 10.x.x.x · 172.16-31.x.x
IPV4 = re.compile(r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b")


def _ozel_ip(mi: re.Match) -> bool:
    a, b = mi.group(1), mi.group(2)
    if a == "10" or (a == "192" and b == "168"):
        return True
    return a == "172" and 16 <= int(b) <= 31
#: Filo içi makine/ajan adları (yayında görünmemeli)
ADLAR = re.compile(r"delinux01|aikonsol|akillibidik|ecepc|ece_pc|[a-z]*-?pi2b01|gozcu|webmaster", re.I)
#: Kişisel mutlak yol
YOL = re.compile(r"/Users/[a-zA-Z]|/home/[a-z][a-z0-9_-]*/")
#: Sır kalıpları
SIR = re.compile(r"sk-[A-Za-z0-9]{10,}|API_SERVER_KEY|API_KEY\s*=\s*['\"]|BEGIN [A-Z ]*PRIVATE KEY")

#: Genel/örnek adresler (hiçbir makineyi göstermez) — bilinçli istisna
IZINLI_ADRES = {"10.0.0.1", "10.0.0.2"}
#: Kendi hijyen kontrolü ve kimlik testleri: içerikleri bu kalıpları KASITLI olarak anar
MUAF = {
    "tests/test_hijyen.py",
    "tests/test_ayarlar.py",
    "tests/test_kurulum.py",
    "tests/desktop/cekirdek.test.mjs",
}


def _dosyalar() -> list[pathlib.Path]:
    cikti = subprocess.run(["git", "ls-files"], cwd=str(KOK), capture_output=True, text=True).stdout
    return [KOK / d for d in cikti.split() if d]


class HijyenKapisi(unittest.TestCase):
    def test_ic_altyapi_izi_yok(self):
        ihlal: list[str] = []
        for p in _dosyalar():
            if not p.is_file():
                continue
            rel = str(p.relative_to(KOK))
            if rel in MUAF:
                continue
            for i, satir in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                for m in IPV4.finditer(satir):
                    if _ozel_ip(m) and m.group(0) not in IZINLI_ADRES:
                        ihlal.append(f"{rel}:{i} tam IP → {m.group(0)}")
                e_ad = ADLAR.search(satir)
                if e_ad:
                    ihlal.append(f"{rel}:{i} makine/ajan adı → {e_ad.group(0)}")
                e_yol = YOL.search(satir)
                if e_yol:
                    ihlal.append(f"{rel}:{i} kişisel yol → {e_yol.group(0)}")
                e_sir = SIR.search(satir)
                if e_sir:
                    ihlal.append(f"{rel}:{i} sır kalıbı → {e_sir.group(0)}")
        self.assertEqual(ihlal, [], "yayın hijyeni ihlali:\n  " + "\n  ".join(ihlal))


if __name__ == "__main__":
    unittest.main()
