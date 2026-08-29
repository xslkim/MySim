#!/usr/bin/env python3
"""tools/t12b_noise_isolate.py — 定位 kv-cache 路径 waypoint 差异来源。

同一输入、同一拼接序列(prompt+生成token+driving query),三种算法比 driving features:
  A  : 原路径 PeftModel(Qwen2ForCausalLM) 全序列前向(含 lm_head, 与 eval 一致)
  B1 : backbone(Qwen2Model) 全序列前向(仅跳 lm_head —— 应为 0 差)
  B2 : backbone prefill+cache 追加前向(测 cache 引入的数值差)
另:A 连跑两次测自一致性(cudnn.benchmark 下是否 bit 稳定)。

  conda run --no-capture-output -n mysim-simlingo python3 tools/t12b_noise_isolate.py
"""
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path("/home/xsl/MySim")
SIMLINGO = ROOT / "external/simlingo"
sys.path.insert(0, str(SIMLINGO))
sys.path.insert(0, str(SIMLINGO / "team_code"))

from t12b_profile_simlingo import build_model, cpu_image_preprocess, cpu_prompt_build, make_driving_input, make_frame, sync  # noqa: E402


def main():
    _, model, tokenizer = build_model()
    llm = model.language_model.model
    backbone = llm.model.model

    rgb = make_frame(100)
    pv = cpu_image_preprocess(rgb)
    ll, _ = cpu_prompt_build(tokenizer, speed=3.2,
                             target_points_np=np.array([[10.0, 0.5], [12.3, -0.4]], dtype=np.float32))
    di = make_driving_input(pv, ll)

    with torch.no_grad():
        # 先跑一遍原路径拿到真实拼接序列长度(不依赖其内部张量,自行重建)
        adaptor_dict = model.adaptors(di, inference=True)
        adaptor_dict = model.vision_model.image_encoder.replace_placeholder_tokens(
            adaptor_dict=adaptor_dict, pixel_values=di.camera_images,
            placeholder_values=di.prompt_inference.placeholder_values, wp_encoder=model.wp_encoder)
        prompt_embeds = adaptor_dict["language_inputs"]          # [1, Lp, H]
        mask = adaptor_dict["language_inputs_mask"]
        Lp = prompt_embeds.size(1)
        n_gen = 17
        gen_embeds = torch.randn(1, n_gen, prompt_embeds.size(2), device="cuda", dtype=torch.bfloat16)
        drv = model.adaptors.driving(di)["inputs"]                # [1, 30, H]
        concat = torch.cat([prompt_embeds, gen_embeds, drv], dim=1)   # [1, Lp+47, H]
        Lt = concat.size(1)
        n_drv = drv.size(1)
        print(f"Lp={Lp} Ltotal={Lt}")

        # A: 原路径风格(CausalLM,output_hidden_states)
        fa = llm(inputs_embeds=concat, attention_mask=None, output_hidden_states=True).hidden_states[-1][:, -n_drv:]
        # A 重跑(自一致)
        fa2 = llm(inputs_embeds=concat, attention_mask=None, output_hidden_states=True).hidden_states[-1][:, -n_drv:]
        # A mask 变体(eval greedy 步里传的是 growing mask;driving 前向不传 mask)
        fam = llm(inputs_embeds=concat, attention_mask=torch.ones(1, Lt, device="cuda", dtype=torch.long),
                  output_hidden_states=True).hidden_states[-1][:, -n_drv:]
        # B1: backbone 全序列(跳 lm_head)
        fb1 = backbone(inputs_embeds=concat, attention_mask=None).last_hidden_state[:, -n_drv:]
        # B2: prefill + cache 追加
        out = backbone(inputs_embeds=concat[:, :Lp], attention_mask=None, use_cache=True)
        pk = out.past_key_values
        out = backbone(inputs_embeds=concat[:, Lp:Lp + n_gen], attention_mask=None, use_cache=True, past_key_values=pk)
        pk = out.past_key_values
        fb2 = backbone(inputs_embeds=drv, attention_mask=None, use_cache=True,
                       past_key_values=pk).last_hidden_state[:, -n_drv:]

        def diff(x, y):
            return (x.float() - y.float()).abs().max().item()

        print(f"A vs A(rerun)      : {diff(fa, fa2):.3e}")
        print(f"A vs A(ones mask)  : {diff(fa, fam):.3e}")
        print(f"A vs B1(no lm_head): {diff(fa, fb1):.3e}")
        print(f"A vs B2(kv-cache)  : {diff(fa, fb2):.3e}")

        # 经过 driving head + cumsum 后的 waypoint 差
        for name, f in [("A", fa), ("B1", fb1), ("B2", fb2)]:
            p = model.adaptors.driving.get_predictions(f)
            if name == "A":
                ref = p
            else:
                print(f"{name}: d_route={diff(ref['route'], p['route']):.3e} d_speed={diff(ref['speed_wps'], p['speed_wps']):.3e}")


if __name__ == "__main__":
    main()
