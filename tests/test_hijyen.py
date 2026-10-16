#!/usr/bin/env python3
"""Yayın hijyeni KAPISI — kamuya açık ağaçta iç altyapı izi ya da sır kalmasın.

Neden var: 16.10.2026'da kamuya açık depoda (9480afb) gerçek bir LAN adresi (192.168.1.9) ve bir
makine adı (delinux01) bulundu; elle tarama yetmiyor çünkü her yeni commit kapıyı yeniden açar.
Bu test ağacı tarar ve ihlali satır satır söyler. Ağ/sır gerektirmez, deterministik, hızlıdır.

İZİN VERİLENLER (sızıntı değil):
  - Kodun KENDİ yerel-aralık listesi (`_YEREL_ISARETLERI`: "192.168.", "10.0." gibi ÖNEKLER) — tam IP değil.
  - Testlerdeki GENEL/örnek adresler: 10.0.0.1 · 10.0.0.2 · RFC 5737 (192.0.2.x) — hiçbir makineyi göstermez.
  - Yazar/kimlik bilgisi (LICENSE, plugin.yaml) ve kamuya açık depo adresleri.

Kullanım notu: kapı `git ls-files` ile İZLENEN dosyaları tarar → commit ÖNCESİ koşacaksan önce
`git add` gerekir (izlenmeyen yeni dosya kapsam dışıdır; ölçüldü 16.10.2026).
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
#: Sır kalıpları — PARÇALARDAN kurulur ki kapı kendi kaynak dosyasını işaretlemesin (aksi hâlde
#: `tests/test_hijyen.py` içindeki kalıp tanımı "sızıntı" sayılırdı; 16.10.2026'da ölçüldü).
_K = "KEY"
SIR = re.compile(
    r"sk-[A-Za-z0-9]{10,}|" + "API_SERVER_" + _K + "|" + "API_" + _K + r"\s*=\s*['\"]|BEGIN [A-Z ]*PRIVATE " + _K
)

#: Genel/örnek adresler (hiçbir makineyi göstermez) — bilinçli istisna
IZINLI_ADRES = {"10.0.0.1", "10.0.0.2"}
#: Bu dosyalarda yalnız AD/ADRES kalıpları muaf (içerikleri bu kalıpları KASITLI olarak anar).
#: **SIR ve YOL her zaman denetlenir** — yoksa kapı kendi test dosyalarında saklanabilir hâle gelir
#: (16.10.2026'da ölçüldü: muaf dosyaya eklenen anahtar satırı kapıyı YEŞİL bırakıyordu).
MUAF_AD_ADRES = {
    "tests/test_hijyen.py",
    "tests/test_ayarlar.py",
    "tests/test_kurulum.py",
    "tests/desktop/cekirdek.test.mjs",
}


def _dosyalar() -> list[pathlib.Path]:
    cikti = subprocess.run(["git", "ls-files"], cwd=str(KOK), capture_output=True, text=True).stdout
    return [KOK / d for d in cikti.split() if d]


def _satir_ihlalleri(rel: str, metin: str) -> list[str]:
    """Tek dosyanın satır satır ihlallerini döndürür — muafiyet DESEN bazlıdır.

    Muaf dosyalarda yalnız AD/ADRES kalıpları serbesttir; **SIR ve YOL her dosyada her zaman** denetlenir
    (yoksa kapı kendi test dosyalarında saklanabilir hâle gelir; 16.10.2026'da ölçüldü).
    """
    muaf_ad = rel in MUAF_AD_ADRES
    out: list[str] = []
    for i, satir in enumerate(metin.splitlines(), 1):
        if not muaf_ad:
            for m in IPV4.finditer(satir):
                if _ozel_ip(m) and m.group(0) not in IZINLI_ADRES:
                    out.append(f"{rel}:{i} tam IP → {m.group(0)}")
            e_ad = ADLAR.search(satir)
            if e_ad:
                out.append(f"{rel}:{i} makine/ajan adı → {e_ad.group(0)}")
            e_yol = YOL.search(satir)
            if e_yol:
                out.append(f"{rel}:{i} kişisel yol → {e_yol.group(0)}")
        e_sir = SIR.search(satir)           # SIR: her dosyada, her zaman
        if e_sir:
            out.append(f"{rel}:{i} sır kalıbı → {e_sir.group(0)}")
    return out


class HijyenKapisi(unittest.TestCase):
    def test_ic_altyapi_izi_yok(self):
        ihlal: list[str] = []
        for p in _dosyalar():
            if not p.is_file():
                continue
            ihlal += _satir_ihlalleri(str(p.relative_to(KOK)),
                                      p.read_text(encoding="utf-8", errors="ignore"))
        self.assertEqual(ihlal, [], "yayın hijyeni ihlali:\n  " + "\n  ".join(ihlal))

    def test_muafiyet_desen_bazli(self):
        """Muaf dosyada AD/ADRES serbest, SIR yasak — kapının kendi kör noktası (16.10.2026).

        akillibidik bağımsız ölçtü: muaf dosyaya konan anahtar satırı kapıyı YEŞİL bırakıyordu.
        """
        anahtar = "API_" + "KEY" + ' = "GERCEK-SIR-1234567890"'
        self.assertTrue(_satir_ihlalleri("tests/test_ayarlar.py", anahtar),
                        "muaf dosyada sır YAKALANMALI")
        self.assertEqual(_satir_ihlalleri("tests/test_ayarlar.py", "# örnek 192.168.1.9 ve delinux01"), [],
                         "muaf dosyada ad/adres serbest olmalı")
        self.assertTrue(_satir_ihlalleri("bekci_core.py", "# 192.168.1.9 ve delinux01"),
                        "muaf olmayan dosyada ad/adres YAKALANMALI")


if __name__ == "__main__":
    unittest.main()
