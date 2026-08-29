#!/usr/bin/env python3
"""tools/t12b_profile_simlingo.py — SimLingo agent 每帧耗时离线拆分(不进 CARLA)。

复刻 team_code/agent_simlingo.py 的 tick/run_step 模型输入构造,用假数据直接跑模型,
分段计时:
  - CPU 图像预处理(jpeg roundtrip + crop + dynamic_preprocess + transform)
  - CPU prompt 构建(conversation.py importlib 重载 + 模板 + tokenize)
  - GPU 视觉编码(InternViT extract_feature)
  - GPU adaptor embed(embedding lookup)
  - GPU greedy_sample(逐 token 全序列前向,记录生成 token 数)
  - GPU 最终 driving 前向(query 拼接待推理)
  - CPU metric_info json dump(模拟不同帧序号下的体量)
另验证:flash-attn 是否生效(LLM/ViT 两侧)、kv-cache 缺失的代价估计(HF use_cache 对照)。

用法(耗时 ~3-5 min,GPU 峰值 ~3GB):
  conda run --no-capture-output -n mysim-simlingo python3 tools/t12b_profile_simlingo.py [--frames 10]
"""

import argparse
import importlib.util
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path("/home/xsl/MySim")
SIMLINGO = ROOT / "external/simlingo"
CKPT = ROOT / "data/checkpoints/simlingo_eval/checkpoints/epoch=013.ckpt/pytorch_model.pt"
HYDRA_CFG = ROOT / "data/checkpoints/simlingo_eval/.hydra/config.yaml"
CONV_PY = ROOT / "external/bench2drive/pretrained/InternVL2-1B/conversation.py"

sys.path.insert(0, str(SIMLINGO))
sys.path.insert(0, str(SIMLINGO / "team_code"))

import cv2
import hydra
import torch.nn.functional as F
from omegaconf import OmegaConf
from PIL import Image
from transformers import AutoConfig, AutoProcessor

from simlingo_training.utils.custom_types import DrivingInput, LanguageLabel
from simlingo_training.utils.internvl2_utils import build_transform, dynamic_preprocess

torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.benchmark = True
torch.backends.cudnn.allow_tf32 = True


def sync():
    torch.cuda.synchronize()


class GpuTimer:
    """monkeypatch 包装器:累计 GPU 段耗时(段内 sync,会有少量同步开销)"""

    def __init__(self):
        self.times = []

    def wrap(self, obj, attr):
        orig = getattr(obj, attr)
        def timed(*a, **kw):
            sync()
            t0 = time.perf_counter()
            out = orig(*a, **kw)
            sync()
            self.times.append((time.perf_counter() - t0) * 1e3)
            return out
        setattr(obj, attr, timed)
        return orig

    def last(self):
        return self.times[-1] if self.times else float("nan")


def median(xs):
    return statistics.median(xs) if xs else float("nan")


def build_model():
    cfg = OmegaConf.load(HYDRA_CFG)
    cfg.model.vision_model.use_global_img = cfg.data_module.use_global_img
    processor = AutoProcessor.from_pretrained(cfg.model.vision_model.variant, trust_remote_code=True)
    tokenizer = processor.tokenizer if "tokenizer" in processor.__dict__ else processor
    tokenizer.add_special_tokens({"additional_special_tokens": [
        "<WAYPOINTS>", "<WAYPOINTS_DIFF>", "<ORG_WAYPOINTS_DIFF>", "<ORG_WAYPOINTS>",
        "<WAYPOINT_LAST>", "<ROUTE>", "<ROUTE_DIFF>", "<TARGET_POINT>"]})
    tokenizer.padding_side = "left"

    default_dtype = torch.get_default_dtype()
    torch.set_default_dtype(torch.bfloat16)
    model = hydra.utils.instantiate(
        cfg.model,
        cfg_data_module=cfg.data_module,
        processor=processor,
        cache_dir="pretrained/InternVL2-1B",
        _recursive_=False,
    ).to("cuda")
    torch.set_default_dtype(default_dtype)
    model.load_state_dict(torch.load(CKPT))
    model.eval()
    return cfg, model, tokenizer


def make_frame(seed):
    """复刻 tick() 的图像预处理:1024x512 BGR -> jpeg -> crop -> 2 tiles 448"""
    rng = np.random.default_rng(seed)
    camera = rng.integers(0, 255, size=(512, 1024, 4), dtype=np.uint8)[:, :, :3].copy()
    _, enc = cv2.imencode(".jpg", camera)
    camera = cv2.imdecode(enc, cv2.IMREAD_UNCHANGED)
    rgb = cv2.cvtColor(camera, cv2.COLOR_BGR2RGB)
    rgb = rgb[: int(rgb.shape[0] - (rgb.shape[0] * 4.8) // 16), :, :]
    return rgb  # HWC uint8


def cpu_image_preprocess(rgb):
    """tick() 中 internvl2 分支的 CPU 部分"""
    transform = build_transform(input_size=448)
    image = Image.fromarray(rgb)
    images = dynamic_preprocess(image, image_size=448, use_thumbnail=False, max_num=2)
    pixel_values = [transform(im) for im in images]
    pixel_values = torch.stack(pixel_values)  # [NP, 3, 448, 448]
    return pixel_values


def cpu_prompt_build(tokenizer, speed, target_points_np):
    """tick() 的 prompt 构建:每帧 importlib 重载 conversation.py + 模板 + tokenize"""
    conversation_all = [
        {"role": "user", "content": [{"type": "text",
         "text": f"Current speed: {speed} m/s. Target waypoint: <TARGET_POINT><TARGET_POINT>. What should the ego do next?"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Waypoints:"}]},
    ]
    spec = importlib.util.spec_from_file_location("get_conv_template", str(CONV_PY))
    conv_module = importlib.util.module_from_spec(spec)
    sys.modules["get_conv_template"] = conv_module
    spec.loader.exec_module(conv_module)

    tmp_config = AutoConfig.from_pretrained("OpenGVLab/InternVL2-1B", trust_remote_code=True)
    image_size = tmp_config.force_image_size or tmp_config.vision_config.image_size
    patch_size = tmp_config.vision_config.patch_size
    num_image_token = int((image_size // patch_size) ** 2 * (tmp_config.downsample_ratio ** 2))

    template = conv_module.get_conv_template("internlm2-chat")
    template.append_message(template.roles[0], "<image>\n" + conversation_all[0]["content"][0]["text"])
    template.append_message(template.roles[1], None)
    query = template.get_prompt()
    system_prompt = template.system_template.replace("{system_message}", template.system_message) + template.sep
    query = query.replace(system_prompt, "")
    image_tokens = "<img>" + "<IMG_CONTEXT>" * num_image_token * 2 + "</img>"
    query = query.replace("<image>", image_tokens, 1)

    tok = tokenizer([query], padding=True, return_tensors="pt", return_offsets_mapping=True, add_special_tokens=False)
    valid = tok["input_ids"] != tokenizer.pad_token_id
    ll = LanguageLabel(
        phrase_ids=tok["input_ids"].to("cuda"),
        phrase_valid=valid.to("cuda"),
        phrase_mask=valid.to("cuda"),
        placeholder_values=[{tokenizer.convert_tokens_to_ids("<TARGET_POINT>"): target_points_np}],
        language_string=[query],
        loss_masking=None,
    )
    return ll, query


def make_driving_input(pixel_values, ll):
    processed = pixel_values.unsqueeze(0).view(1, 1, pixel_values.shape[0], 3, 448, 448)
    return DrivingInput(
        camera_images=processed.to("cuda").bfloat16(),
        image_sizes=None,
        camera_intrinsics=torch.zeros(1, 3, 3, device="cuda"),
        camera_extrinsics=torch.zeros(1, 4, 4, device="cuda"),
        vehicle_speed=torch.FloatTensor([[3.2]]).to("cuda"),
        target_point=torch.FloatTensor([[10.0, 0.5]]).to("cuda"),
        prompt=ll,
        prompt_inference=ll,
    )


def attn_impl_report(model):
    rep = {}
    # LLM (Qwen2 + LoRA PEFT 包装)
    llm = model.language_model.model
    rep["llm_class"] = type(llm).__name__
    try:
        rep["llm_attn_impl"] = llm.config._attn_implementation
    except AttributeError:
        rep["llm_attn_impl"] = "?"
    attn_classes = {type(m).__name__ for n, m in llm.named_modules() if n.endswith("self_attn")}
    rep["llm_self_attn_classes"] = sorted(attn_classes)
    # ViT
    vit = model.vision_model.image_encoder.model.vision_model
    rep["vit_use_flash_attn_cfg"] = bool(vit.config.use_flash_attn)
    vit_flash = {bool(getattr(m, "use_flash_attn", False)) for m in vit.modules() if hasattr(m, "use_flash_attn")}
    rep["vit_layer_use_flash_attn"] = sorted(vit_flash)
    try:
        import flash_attn  # noqa
        rep["flash_attn_pkg"] = flash_attn.__version__
    except ImportError:
        rep["flash_attn_pkg"] = None
    return rep


def kvcache_estimate(model, seq_len, n_tokens):
    """同一 LLM 用 HF 原生 use_cache=True 贪心解码,估计有 kv-cache 时的逐 token 代价。
    数值结果不与 eval 路径对比,仅测延迟。"""
    llm = model.language_model.model  # PeftModel 包装的 Qwen2ForCausalLM
    hidden = model.language_model.hidden_size
    embeds = torch.randn(1, seq_len, hidden, device="cuda", dtype=torch.bfloat16)
    mask = torch.ones(1, seq_len, device="cuda", dtype=torch.long)
    with torch.no_grad():
        sync(); t0 = time.perf_counter()
        out = llm(inputs_embeds=embeds, attention_mask=mask, use_cache=True)
        pk = out.past_key_values
        sync(); prefill = (time.perf_counter() - t0) * 1e3
        step_times = []
        pos = seq_len
        for _ in range(n_tokens):
            x = torch.randn(1, 1, hidden, device="cuda", dtype=torch.bfloat16)
            mask = torch.ones(1, pos + 1, device="cuda", dtype=torch.long)
            sync(); t0 = time.perf_counter()
            out = llm(inputs_embeds=x, attention_mask=mask, use_cache=True, past_key_values=pk)
            pk = out.past_key_values
            sync(); step_times.append((time.perf_counter() - t0) * 1e3)
            pos += 1
    return prefill, median(step_times)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=10)
    ap.add_argument("--warmup", type=int, default=3)
    args = ap.parse_args()

    t0 = time.perf_counter()
    cfg, model, tokenizer = build_model()
    print(f"[load] {time.perf_counter() - t0:.1f}s")

    rep = attn_impl_report(model)
    print("[attn]", json.dumps(rep))

    # ---- monkeypatch 计时 ----
    t_vision, t_gen, t_llm, t_adapt = GpuTimer(), GpuTimer(), GpuTimer(), GpuTimer()
    t_vision.wrap(model.vision_model.image_encoder.model, "extract_feature")
    t_adapt.wrap(model.adaptors, "forward")
    gen_meta = {}
    orig_greedy = model.language_model.greedy_sample
    def greedy_timed(*a, **kw):
        sync(); t0 = time.perf_counter()
        tokens, embeds = orig_greedy(*a, **kw)
        sync()
        t_gen.times.append((time.perf_counter() - t0) * 1e3)
        gen_meta["n_tokens"] = tokens.shape[1]
        gen_meta["llm_calls_in_gen"] = len(t_llm.times) - gen_meta.get("llm_calls_before", 0)
        return tokens, embeds
    model.language_model.greedy_sample = greedy_timed
    t_llm.wrap(model.language_model, "forward")

    rows = []
    gen_tokens_seen = []
    for i in range(args.warmup + args.frames):
        rgb = make_frame(i)

        sync(); t = time.perf_counter()
        pv = cpu_image_preprocess(rgb)
        t_cpu_img = (time.perf_counter() - t) * 1e3

        t = time.perf_counter()
        ll, query = cpu_prompt_build(tokenizer, speed=3.2, target_points_np=np.array([[10.0, 0.5], [12.3, -0.4]], dtype=np.float32))
        t_cpu_prompt = (time.perf_counter() - t) * 1e3

        di = make_driving_input(pv, ll)

        n_llm_before = len(t_llm.times)
        gen_meta["llm_calls_before"] = n_llm_before
        sync(); t = time.perf_counter()
        with torch.no_grad():
            pred_speed_wps, pred_route, language = model(di)
        sync(); t_model = (time.perf_counter() - t) * 1e3

        t = time.perf_counter()
        text = tokenizer.batch_decode(torch.zeros(1, 1, dtype=torch.long), skip_special_tokens=True)
        _ = text
        t_decode0 = (time.perf_counter() - t) * 1e3

        if i < args.warmup:
            print(f"[warmup {i}] model={t_model:.0f}ms tokens={gen_meta.get('n_tokens')}")
            t_vision.times.clear(); t_gen.times.clear(); t_llm.times.clear(); t_adapt.times.clear()
            continue

        n_llm = len(t_llm.times) - n_llm_before
        gen_tokens_seen.append(gen_meta.get("n_tokens"))
        rows.append({
            "cpu_img": t_cpu_img,
            "cpu_prompt": t_cpu_prompt,
            "model_total": t_model,
            "vision": t_vision.last(),
            "adaptors": t_adapt.last(),
            "greedy_gen": t_gen.last(),
            "n_gen_tokens": gen_meta.get("n_tokens"),
            "n_llm_fwd": n_llm,
            "llm_fwd_total": sum(t_llm.times[n_llm_before:]),
            "frame_total": t_cpu_img + t_cpu_prompt + t_model,
        })
        print(f"[frame {i - args.warmup}] total={rows[-1]['frame_total']:.0f}ms "
              f"(cpu_img={t_cpu_img:.0f} cpu_prompt={t_cpu_prompt:.0f} model={t_model:.0f}) | "
              f"vision={t_vision.last():.0f} gen={t_gen.last():.0f} "
              f"tokens={gen_meta.get('n_tokens')} llm_fwd={n_llm}")

    # ---- metric_info json dump 成本(模拟) ----
    entry = {"acceleration": [0.1, 0.2, 0.3], "angular_velocity": [0.0, 0.0, 0.1],
             "forward_vector": [1.0, 0.0, 0.0], "right_vector": [0.0, 1.0, 0.0],
             "location": [100.5, 200.5, 0.3], "rotation": [0.0, 90.0, 0.0]}
    dump_ms = {}
    for n in (100, 1000, 2000, 4000, 8000):
        d = {str(k): entry for k in range(n)}
        t = time.perf_counter()
        with open("/tmp/t12b_metric_bench.json", "w") as f:
            json.dump(d, f, indent=4)
        dump_ms[n] = (time.perf_counter() - t) * 1e3

    # ---- kv-cache 对照(用实测到的典型序列长/生成数) ----
    n_gen = int(median(gen_tokens_seen)) or 80
    prompt_len = int(ll.phrase_ids.shape[1])
    full_fwd_ms = median([x for r in rows for x in [r["llm_fwd_total"] / max(r["n_llm_fwd"], 1)]])
    prefill_ms, cached_step_ms = kvcache_estimate(model, seq_len=prompt_len, n_tokens=n_gen)

    # ---- 汇总 ----
    def col(name):
        return median([r[name] for r in rows])
    summary = {
        "frames": len(rows),
        "prompt_len_tokens": prompt_len,
        "median_gen_tokens": median(gen_tokens_seen),
        "median_llm_fwd_per_frame": median([r["n_llm_fwd"] for r in rows]),
        "cpu_img_ms": col("cpu_img"),
        "cpu_prompt_ms": col("cpu_prompt"),
        "vision_ms": col("vision"),
        "adaptors_ms": col("adaptors"),
        "greedy_gen_ms": col("greedy_gen"),
        "llm_fwd_total_ms": col("llm_fwd_total"),
        "llm_fwd_per_call_ms": full_fwd_ms,
        "model_total_ms": col("model_total"),
        "frame_total_ms": col("frame_total"),
        "metric_dump_ms": dump_ms,
        "kvcache_estimate": {
            "prefill_ms_at_prompt_len": prefill_ms,
            "cached_step_ms": cached_step_ms,
            "n_gen_tokens": n_gen,
            "est_gen_with_cache_ms": prefill_ms + n_gen * cached_step_ms,
            "est_driving_fwd_with_cache_ms": cached_step_ms * 31,  # 30 个 driving query 拼接待推理≈一次短前向
        },
    }
    out = ROOT / "state/tasks/T1.2b-profile-raw.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"attn": rep, "summary": summary, "rows": rows}, indent=2))
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print(f"[written] {out}")


if __name__ == "__main__":
    main()
