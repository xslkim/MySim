#!/usr/bin/env python3
# tools/t13_automot_import_smoke.py — T1.3 AutoMoT agent "加载路径" 冒烟(不碰 GPU)。
#
# 覆盖:
#   1) ckpt 目录文件清单核验(config/tokenizer/bev_config/model.safetensors)
#   2) ModelArguments/InferenceArguments 解析(AUTOMOT_MODEL_PATH 回退链)
#   3) 全 import 链:team_code.mot_b2d_agent(get_entry_point),含 mot.modeling.automot、
#      evaluation.inference、preprocess.generate_lidar_bev_b2d、transformers.models.qwen3_vl
#   4) tokenizer CPU 加载 + add_special_tokens
#   5) model.safetensors key 审计(safe_open 只读 header,不载张量):bev_encoder.* 键存在性
#   6) leaderboard_evaluator import 探测(pkg_resources 缺口,已知,仅报告不 fail)
#
# 不做:模型实例化 / from_pretrained / CUDA 前向(load_model_mot 内含 assert torch.cuda.is_available,
# 且 GPU 被并行任务锁)。GPU 前向归后续评测 agent。
#
# 用法: conda run --no-capture-output -n mysim-automot python3 tools/t13_automot_import_smoke.py
import os
import sys

ROOT = "/home/xsl/MySim"
AUTOMOT = os.path.join(ROOT, "external/AutoMoT")
CARLA_API = "/home/xsl/carla0915-pythonapi"
CKPT = os.environ.get("AUTOMOT_MODEL_PATH", os.path.join(ROOT, "data/checkpoints/automot"))

# run_evaluation.sh 同款 PYTHONPATH(顺序敏感:Automot/mot 提供 data/automot 包,
# 必须早于任何含 data/ 目录的路径)
for p in [
    os.path.join(AUTOMOT, "Automot/mot"),
    os.path.join(AUTOMOT, "Automot"),
    os.path.join(AUTOMOT, "scenario_runner"),
    os.path.join(AUTOMOT, "leaderboard/team_code"),
    os.path.join(AUTOMOT, "leaderboard"),
    os.path.join(CARLA_API, "carla"),
    CARLA_API,
]:
    if p not in sys.path:
        sys.path.insert(0, p)

# mot_b2d_agent 模块级读取的 env(run_evaluation.sh 同款)
os.environ.setdefault("AUTOMOT_MODEL_PATH", CKPT)
# eval 侧 ModelArguments 的 qwen3vl_path 不回退 AUTOMOT_MODEL_PATH(与 train 侧不同),
# 缺省指向 Automot/checkpoints —— 接线必须同设 QWEN3VL_PATH(或建 Automot/checkpoints 软链)
os.environ.setdefault("QWEN3VL_PATH", CKPT)
os.environ.setdefault("IS_BENCH2DRIVE", "True")
os.environ.setdefault("PLANNER_TYPE", "only_traj")
os.environ.setdefault("SAVE_PATH", "/tmp/t13_smoke_viz/")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

failures = []


def step(name):
    print(f"\n=== [{name}] ===", flush=True)


def check(cond, msg):
    tag = "OK  " if cond else "FAIL"
    print(f"{tag} {msg}", flush=True)
    if not cond:
        failures.append(msg)


# ---------- 1) ckpt 文件清单 ----------
step("1 ckpt manifest")
REQUIRED = [
    "model.safetensors",
    "config.json",
    "bev_config.json",
    "preprocessor_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
]
for f in REQUIRED:
    p = os.path.join(CKPT, f)
    ok = os.path.isfile(p) and os.path.getsize(p) > 0
    check(ok, f"{f} ({os.path.getsize(p) if ok else 'missing'})")
stale_index = os.path.join(CKPT, "model.safetensors.index.json")
if os.path.isfile(stale_index):
    import json as _json
    idx = _json.load(open(stale_index))
    shard_files = sorted(set(idx["weight_map"].values()))
    present = all(os.path.isfile(os.path.join(CKPT, s)) for s in shard_files)
    print(f"NOTE model.safetensors.index.json 引用 {shard_files},文件存在={present}"
          " —— loader(_resolve_safetensor_files)优先单文件 model.safetensors,index 不被读取", flush=True)

# ---------- 2) dataclass 解析 ----------
step("2 ModelArguments/InferenceArguments parse")
try:
    from transformers import HfArgumentParser
    from team_code.automot_utils import ModelArguments, InferenceArguments
    parser = HfArgumentParser((ModelArguments, InferenceArguments))
    model_args, inference_args = parser.parse_args_into_dataclasses(args=[])
    check(model_args.model_path == CKPT, f"model_path={model_args.model_path}")
    check(model_args.qwen3vl_path == CKPT, f"qwen3vl_path={model_args.qwen3vl_path} (回退 AUTOMOT_MODEL_PATH)")
    print(f"INFO inference max_num_tokens={inference_args.max_num_tokens}", flush=True)
except Exception as e:
    check(False, f"dataclass parse: {type(e).__name__}: {e}")

# ---------- 3) 全 import 链 ----------
step("3 agent import chain")
try:
    from team_code.mot_b2d_agent import get_entry_point
    check(get_entry_point() == "MOTAgent", f"get_entry_point()={get_entry_point()}")
except Exception as e:
    import traceback
    traceback.print_exc()
    check(False, f"import team_code.mot_b2d_agent: {type(e).__name__}: {e}")

# ---------- 4) tokenizer CPU 加载 ----------
step("4 tokenizer load (CPU)")
try:
    from transformers import AutoTokenizer
    from data.automot.data_utils import add_special_tokens
    tok = AutoTokenizer.from_pretrained(CKPT)
    tok, new_token_ids, _ = add_special_tokens(tok)
    check(True, f"tokenizer ok, vocab={len(tok)}, new_token_ids={len(new_token_ids)}")
except Exception as e:
    check(False, f"tokenizer: {type(e).__name__}: {e}")

# ---------- 5) model.safetensors key 审计 ----------
step("5 safetensors key audit (header only)")
try:
    from safetensors import safe_open
    st_path = os.path.join(CKPT, "model.safetensors")
    with safe_open(st_path, framework="pt", device="cpu") as f:
        keys = list(f.keys())
    bev_keys = [k for k in keys if k.startswith("bev_encoder.")]
    check(len(bev_keys) > 0, f"bev_encoder.* keys={len(bev_keys)} (agent setup 需提取)")
    check(len(keys) > 500, f"total keys={len(keys)}")
    print(f"INFO sample: {keys[0]} | {bev_keys[0] if bev_keys else '-'}", flush=True)
except Exception as e:
    check(False, f"safetensors audit: {type(e).__name__}: {e}")

# ---------- 6) evaluator import 探测(已知 pkg_resources 缺口,仅报告) ----------
step("6 leaderboard_evaluator import probe")
try:
    import importlib
    importlib.import_module("leaderboard.leaderboard_evaluator")
    print("OK   evaluator imports clean", flush=True)
except Exception as e:
    print(f"EXPECTED-FAIL evaluator import: {type(e).__name__}: {e}", flush=True)
    print("NOTE 修复路径:钉 setuptools==80.9.0,或抄 b2d 补丁改 importlib.metadata(3 行)", flush=True)

print("\n========================================", flush=True)
if failures:
    print(f"SMOKE FAIL ({len(failures)}):", flush=True)
    for f_ in failures:
        print(f"  - {f_}", flush=True)
    sys.exit(1)
print("SMOKE PASS (import 链 + ckpt 清单;GPU 前向未做,归评测 agent)", flush=True)
