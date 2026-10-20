"""離線跑一整輪：用 probe 的原始回應當作網路資料，輸出 App 資料。

用法：PROBE=<probe資料夾>[:<另一個>] python3 tests/local_build.py <輸出資料夾> <state 資料夾>
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from pipeline import build  # noqa: E402
from pipeline.state import State  # noqa: E402
from pipeline.util import now  # noqa: E402
from tests.fake_http import FakeHttp  # noqa: E402

ROUTES = [
    ('support.claude.com/en/articles/12138966', 'claude_relnotes_apps'),
    ('anthropics/claude-code/main/CHANGELOG.md', 'claude_code_changelog'),
    ('registry.npmjs.org/@anthropic-ai', 'claude_code_npm'),
    ('release-notes/overview.md', 'claude_docs_relnotes_md'),
    ('anthropic.com/news', 'anthropic_news'),
    ('help.openai.com/en/articles/6825453', 'chatgpt_relnotes'),
    ('repos/openai/codex/releases', 'codex_releases'),
    ('developers.openai.com/api/docs/changelog', 'openai_api_changelog'),
    ('openai.com/news/rss.xml', 'openai_rss'),
    ('gemini.google/release-notes', 'gemini_relnotes'),
    ('gemini-api/docs/changelog.md.txt', 'gemini_api_changelog_md'),
    ('products/gemini/rss', 'google_blog_gemini_rss'),
    ('repos/google-gemini/gemini-cli/releases', 'gemini_cli_releases'),
    ('x.ai/news', 'xai_news'),
    ('developers/release-notes.md', 'xai_relnotes_md'),
    ('repos/ollama/ollama/releases?', 'ollama_releases'),
    ('repos/comfyanonymous/ComfyUI/releases?', 'comfyui_releases'),
    ('lmstudio.ai/changelog', 'lmstudio_changelog'),
    ('AjaxDriverService', 'nvidia_drivers'),
    ('about-claude/pricing.md', 'claude_docs_pricing_md'),
    ('model-deprecations.md', 'claude_docs_deprec_md'),
    ('models/overview.md', 'claude_docs_models_md'),
    ('gemini-api/docs/pricing.md.txt', 'gemini_api_pricing_md'),
    ('gemini-api/docs/deprecations.md.txt', 'gemini_deprec_md'),
    ('developers.openai.com/api/docs/pricing', 'openai_platform_pricing'),
    ('developers.openai.com/api/docs/deprecations', 'openai_deprec'),
    ('docs.x.ai/developers/pricing.md', 'xai_pricing_md'),
    ('openrouter.ai/api/v1/models', 'openrouter_models'),
    ('status.claude.com/api/v2/summary', 'status_claude'),
    ('status.claude.com/api/v2/incidents', 'status_claude_incidents'),
    ('status.openai.com/api/v2/summary', 'status_openai'),
    ('status.openai.com/api/v2/incidents', 'openai_status_incidents'),
    ('data.x.ai/status/incidents', 'xai_status_incidents'),
    ('data.x.ai/status/uptime', 'xai_status_uptime'),
    ('status.cloud.google.com/incidents.json', 'status_gcloud'),
    ('open.er-api.com', 'fx_er_api'),
    ('claude.com/pricing', 'claude_pricing_page'),
    ('chatgpt.com/pricing', 'chatgpt_pricing'),
    ('gemini.google/subscriptions', 'gemini_subs'),
    ('one.google.com/about/plans', 'google_one_tw'),
    ('x.ai/grok', 'grok_plans'),
    ('itunes.apple.com/lookup', 'itunes_lookup'),
    ('pipeline_tag=text-generation', 'hf_trend_text'),
    ('pipeline_tag=image-text-to-text', 'hf_trend_vlm'),
    ('pipeline_tag=text-to-image', 'hf_trend_t2i'),
    ('pipeline_tag=image-to-image', 'hf_trend_i2i'),
    ('pipeline_tag=text-to-video', 'hf_trend_t2v'),
    ('pipeline_tag=image-to-video', 'hf_trend_i2v'),
    ('unsloth/Qwen3-30B-A3B-GGUF/tree', 'hf_tree_unsloth_qwen3_30b'),
    ('Qwen/Qwen3-30B-A3B/resolve/main/config.json', 'hf_config_qwen3_30b'),
    ('repos/ollama/ollama/releases/latest', 'ollama_latest'),
    ('repos/ggml-org/llama.cpp/releases/latest', 'llamacpp_latest'),
]

out = pathlib.Path(sys.argv[1])
state = pathlib.Path(sys.argv[2])
state.mkdir(parents=True, exist_ok=True)
build_id = build.copy_site(out)
http = FakeHttp(ROUTES)
outputs = build.execute(http, State(state), now(), out / 'data', build_id)
m = outputs['meta.json']
print('week', m['week'], m['week_counts'], 'mine', m['week_mine'])
print('patch health', {k: (v.get('n'), v.get('err')) for k, v in m['health'].get('patches', {}).items()})
print('prices health', m['health'].get('prices'))
print('errors', m['errors'])
print('sizes KB', {f: round((out / 'data' / f).stat().st_size / 1024) for f in build.OUT_FILES})
