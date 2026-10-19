#!/usr/bin/env python3
"""Deterministik, **araç zincirinden bağımsız** yayın paketi.

Neden bu dosya var (ölçülmüş hata, 19.10.2026): `git archive | gzip -n` yalnız gzip
**başlığını** sabitler; tar gövdesi git sürümüne bağlıdır (pax başlıkları, sıralama, tarih
biçimi). Aynı commit iki makinede farklı sha256 verdi:
    git 2.54.0 (Apple) + gzip 487   → 48aab29f…  (145.986 B)
    git 2.53.0         + gzip 1.14  → b4c3cbf6…  (146.493 B)
Yani "aynı commit her makinede aynı baytları verir" iddiası yanlıştı — araç zinciri sabitken
doğruydu. Bu betik tar'ı Python `tarfile` ile kendisi yazar: girdiler `git ls-tree` sırasına
göre, `mtime=0`, `uid/gid=0`, boş `uname/gname`, sabit mod ve **USTAR** biçimi → baytlar
git/gzip sürümünden bağımsız.

İki kimlik:
  1. **İçerik kimliği (kanonik):** `git ls-tree -r --full-tree <ref>` çıktısının sha256'sı.
     Arşiv biçiminden tamamen bağımsızdır; "hangi ağaç" sorusunun cevabı budur.
  2. **Paket sha256'sı (bilgi):** bu betiğin ürettiği tarbol. Sınırı dar tut: baytlar
     **git/gzip sürümünden** bağımsızdır, Python'dan tümüyle değil — `tarfile` USTAR başlıkları
     Python sürümüne bağlıdır. Ölçülen: 3.9.6 ve 3.11.17 aynı sha'yı verdi (`81b9e013…`),
     yani 3.8+ ailesinde pratikte sabit; yine de "araç zincirinden bağımsız" değil,
     "git/gzip'ten bağımsız" demek doğru olan.

Kullanım:
    tools/paketle.py [ref] [cikti]
    tools/paketle.py 004e68fa dist/offpeak-bekci-0.1.7.tar.gz
"""

from __future__ import annotations

import gzip
import hashlib
import io
import subprocess
import sys
import tarfile
from pathlib import Path


def _git(*args: str) -> bytes:
    return subprocess.run(("git",) + args, check=True, capture_output=True).stdout


def surum_oku(ref: str) -> str:
    metin = _git("show", f"{ref}:plugin.yaml").decode("utf-8", "replace")
    for satir in metin.splitlines():
        if satir.startswith("version:"):
            return satir.split(":", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(f"HATA: {ref}:plugin.yaml içinde version satırı yok")


def icerik_kimligi(ref: str) -> tuple[str, int]:
    """`git ls-tree -r --full-tree` çıktısının sha256'sı — arşiv biçiminden bağımsız."""
    ham = _git("ls-tree", "-r", "--full-tree", ref)
    return hashlib.sha256(ham).hexdigest(), len(ham.splitlines())


def paketle(ref: str, hedef: Path) -> dict[str, object]:
    surum = surum_oku(ref)
    onek = f"offpeak-bekci-{surum}/"
    kayitlar = []
    for satir in _git("ls-tree", "-r", "-z", "--full-tree", ref).split(b"\0"):
        if not satir:
            continue
        baslik, _, yol = satir.partition(b"\t")
        mod, tur, sha = baslik.split(b" ")
        if tur != b"blob":
            continue
        kayitlar.append((yol.decode("utf-8"), int(mod, 8), sha.decode()))
    kayitlar.sort(key=lambda k: k[0])  # sıralama: yol (byte düzeni sabit)

    ham = io.BytesIO()
    with tarfile.open(fileobj=ham, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for yol, mod, sha in kayitlar:
            veri = _git("cat-file", "blob", sha)
            bilgi = tarfile.TarInfo(onek + yol)
            bilgi.size = len(veri)
            bilgi.mtime = 0
            bilgi.uid = bilgi.gid = 0
            bilgi.uname = bilgi.gname = ""
            bilgi.mode = 0o755 if mod & 0o111 else 0o644
            bilgi.type = tarfile.REGTYPE
            tar.addfile(bilgi, io.BytesIO(veri))

    hedef.parent.mkdir(parents=True, exist_ok=True)
    with open(hedef, "wb") as fh:  # gzip -n eşdeğeri: mtime=0, dosya adı yok
        with gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0, compresslevel=9) as gz:
            gz.write(ham.getvalue())

    return {
        "surum": surum,
        "ref": ref,
        "kisa": subprocess.run(("git", "rev-parse", "--short=8", ref),
                               capture_output=True, text=True, check=True).stdout.strip(),
        "boyut": hedef.stat().st_size,
        "dosya": len(kayitlar),
        "sha256": hashlib.sha256(hedef.read_bytes()).hexdigest(),
    }


def main(argv: list[str]) -> int:
    ref = argv[1] if len(argv) > 1 else "HEAD"
    hedef = Path(argv[2]) if len(argv) > 2 else None
    if hedef is None:
        hedef = Path("dist") / f"offpeak-bekci-{surum_oku(ref)}.tar.gz"
    sonuc = paketle(ref, hedef)
    kimlik, satir = icerik_kimligi(ref)
    print(f"ref      : {sonuc['ref']} ({sonuc['kisa']})")
    print(f"sürüm    : {sonuc['surum']}")
    print(f"paket    : {hedef} · {sonuc['boyut']} B · {sonuc['dosya']} dosya")
    print(f"sha256   : {sonuc['sha256']}")
    print(f"içerik id: {kimlik}  ({satir} izlenen dosya) ← kanonik kimlik")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
