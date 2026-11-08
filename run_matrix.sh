#!/bin/bash
# usage: run_matrix.sh <model> <mode1> [mode2 ...]   (memory_guided = memory mode + --memory-prompt guided)
cd /workspace/clrev
m=$1; shift
for mode in "$@"; do
  extra=""; rmode=$mode
  if [ "$mode" = "memory_guided" ]; then rmode=memory; extra="--memory-prompt guided"; fi
  out=runs/${m}_${mode}_r1
  [ -d "$out" ] && { echo "skip $out"; continue; }
  python -m clrev.runner run --model $m --mode $rmode $extra --questions data/questions_v2.json --db data/payops.db --db-v2 data/payops_v2.db --drift-after 18 --out $out --memory-dir /workspace/memdirs/${m}_${mode}_r1 > runs/${m}_${mode}_r1.log 2>&1
  grep -E "runner: done" runs/${m}_${mode}_r1.log | sed -E 's/.*runner: //'
done
