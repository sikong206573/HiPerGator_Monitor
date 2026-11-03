#!/usr/bin/env bash
# Execute on HiPerGator. Produces local JSON only; never sends data anywhere.
set -euo pipefail

if ! type module >/dev/null 2>&1; then
  # Non-login scheduled Slurm shells may not initialize the module function.
  if [[ -f /etc/profile.d/modules.sh ]]; then
    source /etc/profile.d/modules.sh
  fi
fi

module load ufrc
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python3 "${script_dir}/collect.py" --account qi855292.ucf --output-dir "${script_dir}/../data"
