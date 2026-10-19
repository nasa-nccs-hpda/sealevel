#!/usr/bin/env bash
# fetch_catalog_data.sh [WORKSPACE]
#
# Input data for the facts-experiment-catalog experiment coupling-585-260603: the Zenodo 7478192 archives named in the
# header of each module's registry YAML, unpacked into the layout `feb check-data` expects. About 33 GB, almost all of it
# the TLM CMIP6 archive (31 GB), which is fetched as 8 parallel byte ranges (a single stream ran at about 9 MB/s here; the
# ranges at 15-45 MB/s) and can be resumed by running the script again.
#
#   SKIP_TLM=1  leave out the 31 GB archive (the tlm-sterodynamics service then cannot run)
#   SKIP_ESL=1  leave out the 1.7 GB extreme-sea-level gauge data
#
# Needs curl and tar. The workspace is the directory created by `feb init` (default: this script's directory).
set -euo pipefail

WS=$(cd "${1:-$(dirname "$0")}" && pwd)
Z=https://zenodo.org/record/7478192/files
D=$WS/data/_downloads
M=$WS/data/module_specific_input_data
mkdir -p "$D" "$WS/data/shared_input_data"

get() {                       # get <archive-name> : resumable single-stream download
  [[ -f "$D/$1.tgz.complete" ]] && return 0
  curl -sSL -C - -o "$D/$1.tgz" "$Z/$1.tgz" && touch "$D/$1.tgz.complete"
}

ranged_download() {           # ranged_download <url> <file> <parts> : fetch <parts> byte ranges in parallel (resumable per part), join into <file>
  local url=$1 f=$2 n=$3 total ch i s e
  total=$(curl -sIL "$url" | awk 'tolower($1)=="content-length:" {n=$2} END {print n+0}' | tr -d '\r')
  (( total > 0 )) || { echo "cannot read the size of $url" >&2; return 1; }
  ch=$(( (total + n - 1) / n ))
  for i in $(seq 0 $((n-1))); do
    s=$((i*ch)); e=$((s+ch-1)); (( e >= total )) && e=$((total-1))
    (
      p=$f.part$i; want=$((e-s+1))
      until [[ $(stat -c %s "$p" 2>/dev/null || echo 0) -ge $want ]]; do
        have=$(stat -c %s "$p" 2>/dev/null || echo 0)
        curl -sSL -r $((s+have))-$e -o "$p.tmp" "$url" && cat "$p.tmp" >> "$p"; rm -f "$p.tmp"
      done
    ) &
  done
  wait
  : > "$f"
  for i in $(seq 0 $((n-1))); do cat "$f.part$i" >> "$f"; done
  [[ $(stat -c %s "$f") -eq $total ]] || { echo "size mismatch for $f" >&2; return 1; }
  rm -f "$f".part*
}

unpack() {                    # unpack <archive-name> <target dir under module_specific_input_data | shared_input_data>
  mkdir -p "$2"
  tar xzf "$D/$1.tgz" -C "$2" 2>/dev/null     # tar prints harmless "unknown extended header" warnings; errors still stop the script
}

# archive                                   -> module directory
declare -a MAP=(
  "bamber19_icesheets_preprocess_data         $M/bamber19-icesheets"
  "fair_temperature_fit_data                  $M/fair-temperature"
  "fair_temperature_preprocess_data           $M/fair-temperature"
  "deconto21_AIS_preprocess_data              $M/deconto21-ais"
  "FittedISMIP_icesheet_fit_data              $M/fittedismip-gris"
  "larmip_icesheet_fit_data                   $M/larmip-ais"
  "larmip_icesheet_project_data               $M/larmip-ais"
  "ipccar5_climate_data                       $M/ipccar5-glaciers"
  "ipccar5_glaciers_project_data              $M/ipccar5-glaciers"
  "tlm_sterodynamics_preprocess_data          $M/tlm-sterodynamics"
  "kopp14_verticallandmotion_preprocess_data  $M/kopp14-verticallandmotion"
  "ssp_landwaterstorage_preprocess_data       $M/ssp-landwaterstorage"
  "ssp_landwaterstorage_postprocess_data      $M/ssp-landwaterstorage"
  "grd_fingerprints_data                      $WS/data/shared_input_data"
)
for row in "${MAP[@]}"; do
  read -r name dest <<<"$row"
  get "$name"; unpack "$name" "$dest"
done
# emulandice reads only the shared fingerprints, but the generated script still mounts these directories
mkdir -p "$M/emulandice" "$M/emulandice-ais" "$M/emulandice-gris" "$M/emulandice-glaciers"
# FEB's choice of the ipccar5-glaciers data directory depends on whether a directory named ipccar5 exists: without one the generated script mounts the
# non-existent .../ipccar5, with one it mounts .../ipccar5-glaciers. So link it. `feb check-data` then also reports a module `ipccar5-icesheets` with
# missing files; that module is not part of this experiment, ignore it.
[[ -e "$M/ipccar5" ]] || ln -s ipccar5-glaciers "$M/ipccar5"

if [[ -z "${SKIP_ESL:-}" ]]; then
  get extremesealevel_pointsoverthreshold_fulldata
  unpack extremesealevel_pointsoverthreshold_fulldata "$M/extremesealevel-pointsoverthreshold"
  # the archive holds gesla_data/, the registry's default directory name is gesla_data_full
  [[ -e "$M/extremesealevel-pointsoverthreshold/gesla_data_full" ]] || ln -s gesla_data "$M/extremesealevel-pointsoverthreshold/gesla_data_full"
fi

if [[ -z "${SKIP_TLM:-}" ]]; then
  F=$D/tlm_sterodynamics_cmip6_data.tgz
  [[ -f "$F.complete" ]] || { ranged_download "$Z/tlm_sterodynamics_cmip6_data.tgz" "$F" 8; touch "$F.complete"; }
  mkdir -p "$M/tlm-sterodynamics"
  [[ -f "$M/tlm-sterodynamics/cmip6/.complete" ]] || {
    tar xzf "$F" -C "$M/tlm-sterodynamics" 2>/dev/null
    touch "$M/tlm-sterodynamics/cmip6/.complete"     # sentinel for run_coupling.py --gate
  }
fi
echo "data in place under $WS/data; next: feb check-data"
