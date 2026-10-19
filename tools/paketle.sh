#!/usr/bin/env bash
# Deterministik yayın paketi — herkes aynı sha256'yı üretebilsin.
#
# Neden: paketleyici repoda yokken hiç kimse (peer denetimi dahil) tarbol sha'sını yeniden
# üretemiyor; bu yüzden sha iddiası doğrulanamıyordu (19.10 ölçümü). `gzip -n` dosya adı ve
# zaman damgasını gzip başlığına yazmaz; `git archive` de ağaç + commit zamanından deterministik
# tar üretir → aynı commit her makinede aynı baytları verir.
#
# Kullanım:
#   tools/paketle.sh [ref] [cikti]
#   tools/paketle.sh v0.1.7 dist/offpeak-bekci-0.1.7.tar.gz
#
# Doğrulama (bağımsız):
#   tools/paketle.sh 004e68fa /tmp/x.tar.gz && shasum -a 256 /tmp/x.tar.gz
set -euo pipefail

ref="${1:-HEAD}"
# BSD sed `\?` desteklemez (macOS) → yalnız tırnaklı biçim aranır, o da tek satırlıktır.
surum="$(git show "${ref}:plugin.yaml" | sed -n 's/^version:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"
[ -n "$surum" ] || { echo "HATA: plugin.yaml içinde version bulunamadı (ref=$ref)" >&2; exit 2; }

cikti="${2:-dist/offpeak-bekci-${surum}.tar.gz}"
mkdir -p "$(dirname "$cikti")"

git archive --format=tar --prefix="offpeak-bekci-${surum}/" "$ref" | gzip -9 -n > "$cikti"

printf 'ref    : %s (%s)\n' "$ref" "$(git rev-parse --short=8 "$ref")"
printf 'sürüm  : %s\n' "$surum"
printf 'paket  : %s · %s B\n' "$cikti" "$(wc -c < "$cikti" | tr -d ' ')"
printf 'girdi  : %s (dosya %s · dizin %s)\n' \
  "$(tar -tzf "$cikti" | wc -l | tr -d ' ')" \
  "$(tar -tvzf "$cikti" | grep -vc '^d' || true)" \
  "$(tar -tvzf "$cikti" | grep -c '^d' || true)"
printf 'cache  : %s\n' "$(tar -tzf "$cikti" | grep -cE '__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache' || true)"
printf 'sha256 : %s\n' "$(shasum -a 256 "$cikti" | cut -d' ' -f1)"
