#!/usr/bin/env bash
# 準備翻譯器：llama.cpp（CPU 版）＋ Qwen3 8B 開源模型。下載一次後由 GitHub 快取保存。
set -uo pipefail
D="$HOME/.cache/meta-llm"
mkdir -p "$D"
LOG=/tmp/llm_setup.log
exec > >(tee -a "$LOG") 2>&1
echo "== setup $(date -u +%FT%TZ) cpu=$(nproc) mem=$(free -g | awk '/Mem/{print $2}')G disk=$(df -h ~ | awk 'NR==2{print $4}')"

if [ ! -x "$D/bin/llama-server" ]; then
  # 1) 官方預先編好的 CPU 版
  rel=$(curl -sSL -H "Authorization: Bearer ${GH_TOKEN:-}" -H "Accept: application/vnd.github+json" \
        https://api.github.com/repos/ggml-org/llama.cpp/releases/latest 2>&1)
  echo "release: $(echo "$rel" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("tag_name"), d.get("message",""))' 2>&1 | head -c 200)"
  echo "linux assets: $(echo "$rel" | python3 -c 'import json,sys; print(" ".join(a["name"] for a in json.load(sys.stdin).get("assets",[]) if "ubuntu" in a["name"] or "linux" in a["name"]))' 2>&1 | head -c 600)"
  url=$(echo "$rel" | python3 -c 'import json,sys,re; a=[x["browser_download_url"] for x in json.load(sys.stdin).get("assets",[]) if re.search(r"bin-ubuntu-x64\.(zip|tar\.gz)$", x["name"])]; print(a[0] if a else "")' 2>/dev/null)
  echo "llama.cpp: $url"
  if [ -n "$url" ]; then
    rm -rf /tmp/llama && mkdir -p /tmp/llama/x
    if curl -fsSL --retry 3 "$url" -o /tmp/llama/pkg; then
      case "$url" in
        *.zip) unzip -q /tmp/llama/pkg -d /tmp/llama/x ;;
        *) tar -xzf /tmp/llama/pkg -C /tmp/llama/x ;;
      esac
      srv=$(find /tmp/llama/x -type f -name llama-server | head -1)
      echo "llama-server found at: $srv"
      if [ -n "$srv" ]; then
        mkdir -p "$D/bin" && cp -a "$(dirname "$srv")"/. "$D/bin/" && chmod +x "$D/bin/llama-server"
        LD_LIBRARY_PATH="$D/bin" "$D/bin/llama-server" --version 2>&1 | tail -2 || true
      fi
    fi
  fi
  # 2) 找不到就自己編譯（只編一次，之後放快取）
  if [ ! -x "$D/bin/llama-server" ]; then
    echo "building llama.cpp from source"
    rm -rf /tmp/llama-src
    git clone -q --depth 1 https://github.com/ggml-org/llama.cpp /tmp/llama-src && \
    cmake -S /tmp/llama-src -B /tmp/llama-src/build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
      -DGGML_NATIVE=OFF -DGGML_AVX2=ON -DGGML_FMA=ON -DGGML_F16C=ON -DLLAMA_CURL=OFF > /tmp/llama-cmake.log 2>&1 && \
    cmake --build /tmp/llama-src/build --target llama-server -j "$(nproc)" > /tmp/llama-build.log 2>&1
    echo "build rc=$? $(tail -3 /tmp/llama-build.log | tr '\n' ' ')"
    if [ -x /tmp/llama-src/build/bin/llama-server ]; then
      mkdir -p "$D/bin" && cp /tmp/llama-src/build/bin/llama-server "$D/bin/"
    fi
  fi
fi

MODEL=Qwen3-8B-Q4_K_M
if [ "$(cat "$D/model.txt" 2>/dev/null)" != "$MODEL" ]; then
  rm -f "$D/model.gguf" "$D/model.txt"
fi
if [ ! -s "$D/model.gguf" ]; then
  for u in \
    "https://huggingface.co/Qwen/Qwen3-8B-GGUF/resolve/main/$MODEL.gguf" \
    "https://huggingface.co/unsloth/Qwen3-8B-GGUF/resolve/main/$MODEL.gguf" \
    "https://huggingface.co/lmstudio-community/Qwen3-8B-GGUF/resolve/main/$MODEL.gguf"; do
    echo "model: trying $u"
    curl -fL --retry 3 --retry-delay 5 -sS "$u" -o "$D/model.gguf.part"; rc=$?
    echo "curl rc=$rc size=$(stat -c%s "$D/model.gguf.part" 2>/dev/null)"
    if [ $rc -eq 0 ] && [ "$(stat -c%s "$D/model.gguf.part")" -gt 3000000000 ]; then
      mv "$D/model.gguf.part" "$D/model.gguf"
      echo "$MODEL" > "$D/model.txt"
      break
    fi
    rm -f "$D/model.gguf.part"
  done
fi

ls -la "$D" "$D/bin" 2>/dev/null | head -30
if [ -x "$D/bin/llama-server" ] && [ -s "$D/model.gguf" ]; then
  echo "ready=true" >> "${GITHUB_OUTPUT:-/dev/null}"
  echo "translator files ready: $(cat "$D/model.txt" 2>/dev/null)"
else
  echo "ready=false" >> "${GITHUB_OUTPUT:-/dev/null}"
  echo "translator files missing"
fi
