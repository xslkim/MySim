#!/usr/bin/env python3
"""tools/t12b_overhead_split.py — 区分 LLM 前向 87/40ms 的构成:CPU 入队 vs GPU 完成;lm_head 浪费量化。

  conda run --no-capture-output -n mysim-simlingo python3 tools/t12b_overhead_split.py
"""
import statistics
import sys
import time
from pathlib import Path

import torch

ROOT = Path("/home/xsl/MySim")
SIMLINGO = ROOT / "external/simlingo"
sys.path.insert(0, str(SIMLINGO))
sys.path.insert(0, str(SIMLINGO / "team_code"))

from t12b_profile_simlingo import build_model, sync  # noqa: E402


def med(xs):
    return statistics.median(xs)


def main():
    _, model, tokenizer = build_model()
    llm = model.language_model.model          # PeftModelForCausalLM(Qwen2ForCausalLM)
    backbone = llm.model.model                # LoraModel.model -> Qwen2Model? 视 peft 版本
    print("backbone type:", type(backbone).__name__)
    hidden = model.language_model.hidden_size
    L = 600
    embeds = torch.randn(1, L, hidden, device="cuda", dtype=torch.bfloat16)
    mask = torch.ones(1, L, device="cuda", dtype=torch.long)

    with torch.no_grad():
        # warmup
        for _ in range(3):
            llm(inputs_embeds=embeds, attention_mask=mask, output_hidden_states=True)
        sync()

        # 1) 入队耗时(不 sync):连续 20 次,只测 enqueue;最后一次 sync 得总完成时间
        t0 = time.perf_counter()
        for _ in range(20):
            out = llm(inputs_embeds=embeds, attention_mask=mask, output_hidden_states=True)
        t_enq = (time.perf_counter() - t0) * 1e3 / 20
        sync()
        t_all = (time.perf_counter() - t0) * 1e3 / 20
        print(f"CausalLM full L={L}: enqueue={t_enq:.1f}ms/call, wall(incl gpu)={t_all:.1f}ms/call")

        # 2) 直连 backbone(Qwen2Model,跳过 lm_head)
        for _ in range(3):
            backbone(inputs_embeds=embeds, attention_mask=mask, output_hidden_states=True)
        sync()
        ts = []
        for _ in range(10):
            sync(); t0 = time.perf_counter()
            backbone(inputs_embeds=embeds, attention_mask=mask, output_hidden_states=True)
            sync(); ts.append((time.perf_counter() - t0) * 1e3)
        print(f"backbone-only full L={L}: {med(ts):.1f}ms")

        # 3) lm_head 全序列投影单独计时(hidden[1,600,896] @ weight[151655,896].T)
        hs = torch.randn(1, L, hidden, device="cuda", dtype=torch.bfloat16)
        lm_head_w = llm.get_output_embeddings().weight  # [vocab, hidden]
        for _ in range(3):
            torch.nn.functional.linear(hs, lm_head_w)
        sync()
        ts = []
        for _ in range(10):
            sync(); t0 = time.perf_counter()
            torch.nn.functional.linear(hs, lm_head_w)
            sync(); ts.append((time.perf_counter() - t0) * 1e3)
        print(f"lm_head full-seq projection L={L}: {med(ts):.1f}ms (alloc [1,{L},151655] bf16 = {L*151655*2/1e6:.0f}MB)")

        # 4) cached step:enqueue vs wall
        r = llm(inputs_embeds=embeds, attention_mask=mask, use_cache=True)
        pk = r.past_key_values
        x = torch.randn(1, 1, hidden, device="cuda", dtype=torch.bfloat16)
        mask1 = torch.ones(1, L + 1, device="cuda", dtype=torch.long)
        for _ in range(3):
            llm(inputs_embeds=x, attention_mask=mask1, use_cache=True, past_key_values=pk)
        sync()
        t0 = time.perf_counter()
        for _ in range(20):
            llm(inputs_embeds=x, attention_mask=mask1, use_cache=True, past_key_values=pk)
        t_enq = (time.perf_counter() - t0) * 1e3 / 20
        sync()
        t_all = (time.perf_counter() - t0) * 1e3 / 20
        print(f"cached step: enqueue={t_enq:.1f}ms/call, wall={t_all:.1f}ms/call")

        # 5) backbone cached step(跳 lm_head)
        r = backbone(inputs_embeds=embeds, attention_mask=mask, use_cache=True)
        pk2 = r.past_key_values
        for _ in range(3):
            backbone(inputs_embeds=x, attention_mask=mask1, use_cache=True, past_key_values=pk2)
        sync()
        ts = []
        for _ in range(10):
            sync(); t0 = time.perf_counter()
            backbone(inputs_embeds=x, attention_mask=mask1, use_cache=True, past_key_values=pk2)
            sync(); ts.append((time.perf_counter() - t0) * 1e3)
        print(f"backbone cached step: {med(ts):.1f}ms")


if __name__ == "__main__":
    main()
