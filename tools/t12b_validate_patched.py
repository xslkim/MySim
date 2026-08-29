#!/usr/bin/env python3
"""tools/t12b_validate_patched.py — T1.2b 补丁后离线数值验证(不进 CARLA)。

同一模型同一假数据输入(8 帧),四个配置:
  REF0  : 官方原路径语义(greedy_sample_legacy 逐 token 全序列重算 + driving 整序列重算),
          LoRA 未 merge;lm_head 死代码已证 features diff=0,故此路即官方原路径 bit 等价
  FAST0 : 补丁后 kv-cache 路径(model(di), eval_fastpath=True),LoRA 未 merge —— 隔离 B1
  REF1  : 官方原路径语义,LoRA merge 后 —— 隔离 B2(merge 本身的权重舍入差)
  FAST1 : kv-cache + LoRA merge(= 评测 agent 实际形态)—— B1+B2

判定(profile 口径复测,不追求 0):生成文本一致性、speed_wps/route 最大绝对差应落在
profile 报告量级(waypoints max diff 0.25–0.9m,偶发 token 翻转)。

  conda run --no-capture-output -n mysim-simlingo python3 tools/t12b_validate_patched.py
"""
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path("/home/xsl/MySim")
SIMLINGO = ROOT / "external/simlingo"
sys.path.insert(0, str(SIMLINGO))
sys.path.insert(0, str(SIMLINGO / "team_code"))

from t12b_profile_simlingo import build_model, cpu_image_preprocess, cpu_prompt_build, make_driving_input, make_frame, sync  # noqa: E402


def original_driving_pass(model, di, max_new_tokens=100):
    """官方原路径语义复刻(无 cache 逐 token 重算 + driving 整序列重算)。"""
    adaptor_dict = model.adaptors(di, inference=True)
    adaptor_dict = model.vision_model.image_encoder.replace_placeholder_tokens(
        adaptor_dict=adaptor_dict,
        pixel_values=di.camera_images,
        placeholder_values=di.prompt_inference.placeholder_values,
        wp_encoder=model.wp_encoder,
    )
    input_embed = adaptor_dict["language_inputs"][0].unsqueeze(0)
    attention_mask = adaptor_dict["language_inputs_mask"][0].unsqueeze(0)

    lm = model.language_model
    eos = model.tokenizer.eos_token_id  # InternVL2-1B 走 driving.py 的 else 分支
    sampled, embeds = lm.greedy_sample_legacy(
        input_embed,
        eos_token_id=eos,
        max_new_tokens=max_new_tokens,
        input_embed_matrix=model.adaptors.language.embed_tokens.weight,
        logit_matrix=model.adaptors.language.lm_head.weight,
        attention_mask=attention_mask,
    )
    inputs_driving = model.adaptors.driving(di)
    concat = torch.cat((embeds, inputs_driving["inputs"][0].unsqueeze(0)), dim=1)
    features, _ = lm.forward(concat)
    n = inputs_driving["inputs"].size(1)
    preds = model.adaptors.driving.get_predictions(features[:, -n:])
    text = model.tokenizer.batch_decode(sampled, skip_special_tokens=True)[0]
    return preds["speed_wps"].cpu(), preds["route"].cpu(), text, sampled.size(1)


def fast_pass(model, di):
    """补丁后路径:DrivingModel.forward(eval_fastpath=True)。"""
    sp, rt, lang = model(di)
    return sp.cpu(), rt.cpu(), lang[0], None


def timed(fn, *a):
    with torch.no_grad():
        sync(); t = time.perf_counter()
        out = fn(*a)
        sync()
    return out, (time.perf_counter() - t) * 1e3


def diff(a, b):
    return (a.float() - b.float()).abs().max().item()


def main():
    n_frames = 8
    t0 = time.perf_counter()
    _, model, tokenizer = build_model()
    model.eval_fastpath = True  # 补丁后新路径(env 无关,显式钉死)
    print(f"[load] {time.perf_counter() - t0:.1f}s (LoRA 未 merge)")

    frames = []
    for i in range(n_frames):
        rgb = make_frame(100 + i)
        pv = cpu_image_preprocess(rgb)
        ll, _ = cpu_prompt_build(tokenizer, speed=round(1.5 + i * 0.7, 1),
                                 target_points_np=np.array([[10.0 + i, 0.5 - i * 0.2], [12.3 + i, -0.4]],
                                                           dtype=np.float32))
        frames.append(make_driving_input(pv, ll))

    # ---- pass 1:REF0 / FAST0(均未 merge) ----
    rows = []
    for i, di in enumerate(frames):
        (sp_r, rt_r, tx_r, ntok), t_r = timed(original_driving_pass, model, di)
        (sp_f, rt_f, tx_f, _), t_f = timed(fast_pass, model, di)
        rows.append({
            "frame": i, "n_tokens": ntok,
            "ref0": (sp_r, rt_r, tx_r), "fast0": (sp_f, rt_f, tx_f),
            "t_ref0_ms": t_r, "t_fast0_ms": t_f,
        })
        print(f"[f{i}] REF0={t_r:.0f}ms FAST0={t_f:.0f}ms tokens={ntok} "
              f"text_same={tx_r == tx_f} d_wps={diff(sp_r, sp_f):.3f} d_route={diff(rt_r, rt_f):.3f}")

    # ---- merge LoRA → pass 2:REF1 / FAST1(评测 agent 实际形态) ----
    lm = model.language_model
    assert getattr(lm, "lora", False) and hasattr(lm.model, "merge_and_unload")
    t0 = time.perf_counter()
    lm.model = lm.model.merge_and_unload()
    print(f"[merge] {time.perf_counter() - t0:.1f}s → {type(lm.model).__name__}")

    for i, di in enumerate(frames):
        (sp_r, rt_r, tx_r, _), t_r = timed(original_driving_pass, model, di)
        (sp_f, rt_f, tx_f, _), t_f = timed(fast_pass, model, di)
        rows[i].update({
            "ref1": (sp_r, rt_r, tx_r), "fast1": (sp_f, rt_f, tx_f),
            "t_ref1_ms": t_r, "t_fast1_ms": t_f,
        })
        print(f"[f{i}] REF1={t_r:.0f}ms FAST1={t_f:.0f}ms "
              f"text_same={tx_r == tx_f} d_wps={diff(sp_r, sp_f):.3f} d_route={diff(rt_r, rt_f):.3f}")

    def med(xs):
        return statistics.median(xs)

    def cmp(key_a, key_b):
        return {
            "text_all_same": all(r[key_a][2] == r[key_b][2] for r in rows),
            "max_d_speed_wps": max(diff(r[key_a][0], r[key_b][0]) for r in rows),
            "max_d_route": max(diff(r[key_a][1], r[key_b][1]) for r in rows),
        }

    summ = {
        "n_frames": n_frames,
        "B1_isolated__fast0_vs_ref0": cmp("fast0", "ref0"),
        "B2_isolated__ref1_vs_ref0": cmp("ref1", "ref0"),
        "B1_on_merged__fast1_vs_ref1": cmp("fast1", "ref1"),
        "B1B2_total__fast1_vs_ref0": cmp("fast1", "ref0"),
        "timing": {
            "median_ref0_ms": med([r["t_ref0_ms"] for r in rows]),
            "median_fast0_ms": med([r["t_fast0_ms"] for r in rows]),
            "median_ref1_ms": med([r["t_ref1_ms"] for r in rows]),
            "median_fast1_ms": med([r["t_fast1_ms"] for r in rows]),
            "speedup_unmerged": med([r["t_ref0_ms"] for r in rows]) / med([r["t_fast0_ms"] for r in rows]),
            "speedup_merged_vs_orig": med([r["t_ref0_ms"] for r in rows]) / med([r["t_fast1_ms"] for r in rows]),
        },
        "n_tokens": [r["n_tokens"] for r in rows],
    }
    print("\n=== SUMMARY ===")
    print(json.dumps(summ, indent=2, ensure_ascii=False))

    out_rows = []
    for r in rows:
        out_rows.append({
            "frame": r["frame"], "n_tokens": r["n_tokens"],
            "t_ref0_ms": r["t_ref0_ms"], "t_fast0_ms": r["t_fast0_ms"],
            "t_ref1_ms": r["t_ref1_ms"], "t_fast1_ms": r["t_fast1_ms"],
            "text_same_fast0_ref0": r["fast0"][2] == r["ref0"][2],
            "text_same_fast1_ref0": r["fast1"][2] == r["ref0"][2],
            "d_speed_fast0_ref0": diff(r["fast0"][0], r["ref0"][0]),
            "d_route_fast0_ref0": diff(r["fast0"][1], r["ref0"][1]),
            "d_speed_fast1_ref0": diff(r["fast1"][0], r["ref0"][0]),
            "d_route_fast1_ref0": diff(r["fast1"][1], r["ref0"][1]),
            "text_ref0": r["ref0"][2], "text_fast1": r["fast1"][2],
        })
    out = ROOT / "state/tasks/T1.2b-validate-patched.json"
    out.write_text(json.dumps({"summary": summ, "rows": out_rows}, indent=2, ensure_ascii=False))
    print(f"[written] {out}")


if __name__ == "__main__":
    main()
