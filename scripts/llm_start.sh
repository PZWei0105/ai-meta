#!/usr/bin/env bash
# 在背景啟動翻譯器（llama-server），等它準備好；失敗也不讓整輪更新中斷。
set -uo pipefail
exec > >(tee -a /tmp/llm_setup.log) 2>&1
D="$HOME/.cache/meta-llm"
if [ ! -x "$D/bin/llama-server" ] || [ ! -s "$D/model.gguf" ]; then
  echo "translator not available, news will stay in original language this round"
  exit 0
fi
export LD_LIBRARY_PATH="$D/bin:${LD_LIBRARY_PATH:-}"
nohup "$D/bin/llama-server" -m "$D/model.gguf" --host 127.0.0.1 --port 8088 \
  -c 16384 -np 4 -t "$(nproc)" > /tmp/llama.log 2>&1 &
echo "META_LLM_MODEL=$(cat "$D/model.txt" 2>/dev/null)" >> "${GITHUB_ENV:-/dev/null}"
for i in $(seq 1 120); do
  if curl -sf http://127.0.0.1:8088/health > /dev/null; then
    echo "translator ready after ${i}x2s"
    exit 0
  fi
  sleep 2
done
echo "translator did not start"
tail -40 /tmp/llama.log
exit 0
