"""Python (`bekci_core.py`) <-> JS (`desktop/bekci-cekirdek.js`) parite testi (stdlib).

Masaüstü rozeti pencere matematiğini JS'te, gecikme/kuyruk politikası Python'da
uygular. İki uygulama aynı anlar için aynı sonucu vermezse rozet yalan söyler;
bu test aynı an kümesini iki dilde koşturup alan alan karşılaştırır.

Çalıştırma: `python3 -m unittest tests.test_parite -v`  (node gerekir)
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

import bekci_core as c  # noqa: E402

ANLAR = [
    "2026-10-19T11:59:59+00:00",
    "2026-10-19T12:00:00+00:00",
    "2026-10-19T17:00:00+00:00",
    "2026-10-19T17:30:00+00:00",
    "2026-10-19T18:00:00+00:00",
    "2026-10-19T23:59:00+00:00",
    "2026-10-20T12:00:00+00:00",
    "2026-10-23T18:30:00+00:00",
    "2026-10-24T00:00:00+00:00",
    "2026-10-24T17:30:00+00:00",
    "2026-10-25T20:00:00+00:00",
    "2026-10-26T11:00:00+00:00",
]

ALANLAR = ("pencere", "peak_mi", "gelecek_pencere", "gelecek_gecis_utc",
           "kalan_sn", "geri_sayim", "t30_icerisinde", "offpeak_anahtari")

JS_OZET = """
import { ozet } from '{modul}'
const anlar = JSON.parse(process.argv[2])
console.log(JSON.stringify(anlar.map(a => {{
  const o = ozet(Date.parse(a))
  return {{
    iso: a, pencere: o.pencere, peak_mi: o.peak_mi, gelecek_pencere: o.gelecek_pencere,
    gelecek_gecis_utc: o.gelecek_gecis_utc, kalan_sn: o.kalan_sn, geri_sayim: o.geri_sayim,
    t30_icerisinde: o.t30_icerisinde, offpeak_anahtari: o.offpeak_anahtari,
  }}
}}))
"""

JS_KUYRUK = """
import { kuyrukAyristir } from '{modul}'
console.log(JSON.stringify(kuyrukAyristir(process.argv[2]).map(x => [x.id, x.durum])))
"""


def norm(z):
    return str(z).replace("+00:00", "Z").replace("z", "Z")


def node_calistir(kod, arg):
    if shutil.which("node") is None:
        raise unittest.SkipTest("node yok")
    modul = (KOK / "desktop" / "bekci-cekirdek.js").as_posix()
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as f:
        f.write(kod.format(modul=modul))
        yol = f.name
    try:
        sonuc = subprocess.run(["node", yol, arg], capture_output=True, text=True, check=False, timeout=60)
    finally:
        Path(yol).unlink(missing_ok=True)
    assert sonuc.returncode == 0, "node hata verdi: " + sonuc.stderr[:400]
    return sonuc.stdout.strip().splitlines()[-1]


class PariteTest(unittest.TestCase):
    def test_pencere_matematigi_ayni(self):
        js = {k["iso"]: k for k in json.loads(node_calistir(JS_OZET, json.dumps(ANLAR)))}
        for iso in ANLAR:
            py = c.ozet(c._dt.datetime.fromisoformat(iso))
            j = js[iso]
            for alan in ALANLAR:
                beklenen = norm(py[alan]) if (alan.endswith("_utc") or alan == "offpeak_anahtari") else py[alan]
                with self.subTest(iso=iso, alan=alan):
                    self.assertEqual(j[alan], beklenen, "JS=%r PY=%r" % (j[alan], py[alan]))

    def test_kuyruk_ayristirma_ayni(self):
        metin = (KOK / "tests" / "kuyruk_ornek.md").read_text(encoding="utf-8")
        js = [tuple(x) for x in json.loads(node_calistir(JS_KUYRUK, metin))]
        py = [(k["id"], k["durum"]) for k in c.kuyruk_ayristir(metin)]
        self.assertEqual(js, py)
        self.assertTrue(py)


if __name__ == "__main__":
    unittest.main(verbosity=2)
