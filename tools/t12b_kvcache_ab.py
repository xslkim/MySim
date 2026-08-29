#!/usr/bin/env python3
"""tools/t12b_kvcache_ab.py — kv-cache 版采样的数值等价性 + 端到端提速 A/B(离线,不改仓库)。

对照两条路径,同一模型同一输入:
  A. 现状:DrivingModel.forward(predict_language=True) — greedy_sample 无 cache,逐 token 全序列前向
  B. 提议:prefill 一次 + HF past_key_values 逐 token 缓存解码,driving query 复用同一 cache 追加前向;
     且跳过 lm_head 全序列投影(直接用 backbone Qwen2Model,logits 只对最后位置手算 —— 与 greedy_sample 相同做法)

判定:
  - 生成 token 序列是否完全一致(greedy argmax)
  - driving head 输出(speed_wps / route)最大绝对差

  conda run --no-capture-output -n mysim-simlingo python3 tools/t12b_kvcache_ab.py
"""
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

ROOT = Path("/home/xsl/MySim")
SIMLINGO = ROOT / "external/simlingo"
sys.path.insert(0, str(SIMLINGO))
sys.path.insert(0, str(SIMLINGO / "team_code"))

from t12b_profile_simlingo import build_model, cpu_image_preprocess, cpu_prompt_build, make_driving_input, make_frame, sync  # noqa: E402


def med(xs):
    return statistics.median(xs)


def cached_driving_pass(model, di, max_new_tokens=100):
    """复刻 DrivingModel.forward(predict_language=True) 的计算,但用 kv-cache。
    返回 (speed_wps, route, sampled_tokens, stats)"""
    lm = model.language_model            # LLM wrapper
    llm = lm.model                       # PeftModelForCausalLM
    backbone = llm.model.model           # Qwen2Model(带 LoRA 注入)
    lm_head_w = model.adaptors.language.lm_head.weight
    embed_w = model.adaptors.language.embed_tokens.weight
    eos = model.tokenizer.eos_token_id

    # 1) adaptor + 图像 placeholder 替换(与原路径相同,含视觉编码)
    adaptor_dict = model.adaptors(di, inference=True)
    adaptor_dict = model.vision_model.image_encoder.replace_placeholder_tokens(
        adaptor_dict=adaptor_dict,
        pixel_values=di.camera_images,
        placeholder_values=di.prompt_inference.placeholder_values,
        wp_encoder=model.wp_encoder,
    )
    input_embeds = adaptor_dict["language_inputs"]          # [1, L, H]
    attention_mask = adaptor_dict["language_inputs_mask"]   # [1, L] bool

    stats = {}
    sync(); t0 = time.perf_counter()
    am = attention_mask.long()
    out = backbone(inputs_embeds=input_embeds, attention_mask=am, use_cache=True)
    pk = out.past_key_values
    last_h = out.last_hidden_state[:, -1]
    stats["prefill_ms"] = 0.0  # filled later
    sync(); stats["prefill_ms"] = (time.perf_counter() - t0) * 1e3

    sampled = []
    t_gen0 = time.perf_counter()
    cur_len = input_embeds.size(1)
    eos_embed = None
    for i in range(max_new_tokens):
        logits = F.linear(last_h, lm_head_w)
        next_tok = logits.argmax(dim=-1)
        sampled.append(next_tok.item())
        if next_tok.item() == eos:
            # 原路径中 eos 的 embedding 也会进入序列(driving query 会 attend 到它),
            # 这里记下,与 driving query 一起进 cache 追加前向
            eos_embed = F.embedding(next_tok.view(1, 1), embed_w)
            break
        x = F.embedding(next_tok.view(1, 1), embed_w)
        am = torch.cat([am, torch.ones(1, 1, device=am.device, dtype=torch.long)], dim=1)
        out = backbone(inputs_embeds=x, attention_mask=am, use_cache=True, past_key_values=pk)
        pk = out.past_key_values
        last_h = out.last_hidden_state[:, -1]
        cur_len += 1
    sync(); stats["decode_ms"] = (time.perf_counter() - t_gen0) * 1e3
    stats["n_tokens"] = len(sampled)

    # 2) driving query 复用 cache 追加前向(原路径是 prompt+生成+driving 全序列重跑)
    inputs_driving = model.adaptors.driving(di)
    drv = inputs_driving["inputs"]            # [1, 30, H]
    if eos_embed is not None:
        drv = torch.cat([eos_embed, drv], dim=1)
    am2 = torch.ones(1, cur_len + drv.size(1), device=drv.device, dtype=torch.long)
    sync(); t0 = time.perf_counter()
    out = backbone(inputs_embeds=drv, attention_mask=am2, use_cache=True, past_key_values=pk)
    sync(); stats["driving_fwd_ms"] = (time.perf_counter() - t0) * 1e3
    features = out.last_hidden_state          # [1, 30, H](只算了新增 30 个位置)
    preds = model.adaptors.driving.get_predictions(features)
    return preds["speed_wps"], preds["route"], sampled, stats


def main():
    _, model, tokenizer = build_model()
    n_frames = 5
    rows = []
    for i in range(n_frames):
        rgb = make_frame(100 + i)
        pv = cpu_image_preprocess(rgb)
        ll, _ = cpu_prompt_build(tokenizer, speed=3.2,
                                 target_points_np=np.array([[10.0, 0.5], [12.3, -0.4]], dtype=np.float32))
        di = make_driving_input(pv, ll)

        # A: 原路径
        sync(); t0 = time.perf_counter()
        with torch.no_grad():
            sp_a, rt_a, lang_a = model(di)
        sync(); t_a = (time.perf_counter() - t0) * 1e3

        # B: kv-cache 路径
        sync(); t0 = time.perf_counter()
        with torch.no_grad():
            sp_b, rt_b, tok_b, st = cached_driving_pass(model, di)
        sync(); t_b = (time.perf_counter() - t0) * 1e3

        # 等价性
        tok_same = tokenizer.batch_decode(
            torch.tensor([tok_b]), skip_special_tokens=True)[0] == lang_a[0]
        dsp = (sp_a - sp_b).abs().max().item()
        drt = (rt_a - rt_b).abs().max().item()
        rows.append({"t_orig_ms": t_a, "t_cache_ms": t_b, "text_same": tok_same,
                     "max_d_speed_wps": dsp, "max_d_route": drt, "n_tokens": st["n_tokens"],
                     **{f"cache_{k}": v for k, v in st.items() if k.endswith("ms")}})
        print(f"[f{i}] orig={t_a:.0f}ms cache={t_b:.0f}ms tokens={st['n_tokens']} "
              f"text_same={tok_same} d_wps={dsp:.2e} d_route={drt:.2e}")

    summ = {
        "median_orig_ms": med([r["t_orig_ms"] for r in rows]),
        "median_cache_ms": med([r["t_cache_ms"] for r in rows]),
        "speedup": med([r["t_orig_ms"] for r in rows]) / med([r["t_cache_ms"] for r in rows]),
        "text_all_same": all(r["text_same"] for r in rows),
        "max_d_speed_wps": max(r["max_d_speed_wps"] for r in rows),
        "max_d_route": max(r["max_d_route"] for r in rows),
        "cache_prefill_ms": med([r["cache_prefill_ms"] for r in rows]),
        "cache_decode_ms": med([r["cache_decode_ms"] for r in rows]),
        "cache_driving_fwd_ms": med([r["cache_driving_fwd_ms"] for r in rows]),
        "n_tokens": [r["n_tokens"] for r in rows],
    }
    print("SUMMARY:", summ)

    import json
    out = ROOT / "state/tasks/T1.2b-kvcache-ab.json"
    out.write_text(json.dumps({"summary": summ, "rows": rows}, indent=2))
    print(f"[written] {out}")


if __name__ == "__main__":
    main()
