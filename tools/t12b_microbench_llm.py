#!/usr/bin/env python3
"""tools/t12b_microbench_llm.py — 拆解 SimLingo LLM 单次前向为何 ~87ms。

测量(同一 Qwen2-0.5B+LoRA, 与 eval 路径同模型):
  A. full forward L=600 (eval greedy 每步形态, inputs_embeds+mask, output_hidden_states=True)
  B. 同 A 但 attention_mask=None(bs=1 无 pad,等效)
  C. 同 A 但 disable_adapter()(排除 LoRA 数学开销,保留 PEFT wrapper)
  D. use_cache 单 token step:L=600 / L=64 / L=8(分离固定开销 vs 序列长开销)
  E. prompt 构建内部拆分:importlib exec_module / AutoConfig(agent 内只跑一次) / 模板 / tokenize

  conda run --no-capture-output -n mysim-simlingo python3 tools/t12b_microbench_llm.py
"""

import importlib.util
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path("/home/xsl/MySim")
SIMLINGO = ROOT / "external/simlingo"
CONV_PY = ROOT / "external/bench2drive/pretrained/InternVL2-1B/conversation.py"
sys.path.insert(0, str(SIMLINGO))
sys.path.insert(0, str(SIMLINGO / "team_code"))

from transformers import AutoConfig

from t12b_profile_simlingo import build_model, sync  # noqa: E402


def med(xs):
    return statistics.median(xs)


def bench(fn, n=10, warmup=3):
    for _ in range(warmup):
        fn()
    ts = []
    for _ in range(n):
        sync()
        t0 = time.perf_counter()
        fn()
        sync()
        ts.append((time.perf_counter() - t0) * 1e3)
    return med(ts)


def main():
    _, model, tokenizer = build_model()
    llm = model.language_model.model  # PeftModel
    hidden = model.language_model.hidden_size
    dev = "cuda"

    print(f"hidden={hidden} layers={llm.config.num_hidden_layers}")

    for L in (600,):
        embeds = torch.randn(1, L, hidden, device=dev, dtype=torch.bfloat16)
        mask = torch.ones(1, L, device=dev, dtype=torch.long)
        with torch.no_grad():
            a = bench(lambda: llm(inputs_embeds=embeds, attention_mask=mask, output_hidden_states=True))
            b = bench(lambda: llm(inputs_embeds=embeds, attention_mask=None, output_hidden_states=True))
            with llm.disable_adapter():
                c = bench(lambda: llm(inputs_embeds=embeds, attention_mask=mask, output_hidden_states=True))
            d = bench(lambda: llm(inputs_embeds=embeds, attention_mask=mask, output_hidden_states=False))
        print(f"L={L} full-fwd: with_mask+hs={a:.1f}ms no_mask={b:.1f}ms no_lora={c:.1f}ms no_hidden_states={d:.1f}ms")

    # kv-cache 单 token step,不同上下文长
    out = {}
    for L in (8, 64, 600):
        embeds = torch.randn(1, L, hidden, device=dev, dtype=torch.bfloat16)
        mask = torch.ones(1, L, device=dev, dtype=torch.long)
        with torch.no_grad():
            r = llm(inputs_embeds=embeds, attention_mask=mask, use_cache=True)
            pk = r.past_key_values
            x = torch.randn(1, 1, hidden, device=dev, dtype=torch.bfloat16)
            def step():
                nonlocal_mask = torch.ones(1, L + 1, device=dev, dtype=torch.long)
                llm(inputs_embeds=x, attention_mask=nonlocal_mask, use_cache=True, past_key_values=pk)
            out[L] = bench(step)
    print("cached 1-token step by ctx len:", {k: f"{v:.1f}ms" for k, v in out.items()})

    # ---- prompt 构建内部拆分(agent 内 AutoConfig 只跑一次) ----
    t = bench(lambda: importlib.util.spec_from_file_location("m", str(CONV_PY)), n=20)
    def exec_mod():
        spec = importlib.util.spec_from_file_location("get_conv_template", str(CONV_PY))
        m = importlib.util.module_from_spec(spec)
        sys.modules["get_conv_template"] = m
        spec.loader.exec_module(m)
    e = bench(exec_mod, n=20)
    ac_first = AutoConfig.from_pretrained("OpenGVLab/InternVL2-1B", trust_remote_code=True)
    ac = bench(lambda: AutoConfig.from_pretrained("OpenGVLab/InternVL2-1B", trust_remote_code=True), n=10)

    spec = importlib.util.spec_from_file_location("get_conv_template", str(CONV_PY))
    conv_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(conv_module)
    prompt_text = "Current speed: 3.2 m/s. Target waypoint: <TARGET_POINT><TARGET_POINT>. What should the ego do next?"
    def template_build():
        template = conv_module.get_conv_template("internlm2-chat")
        template.append_message(template.roles[0], "<image>\n" + prompt_text)
        template.append_message(template.roles[1], None)
        q = template.get_prompt()
        sp = template.system_template.replace("{system_message}", template.system_message) + template.sep
        q = q.replace(sp, "")
        return q.replace("<image>", "<img>" + "<IMG_CONTEXT>" * 512 + "</img>", 1)
    tb = bench(template_build, n=20)
    q = template_build()
    tk = bench(lambda: tokenizer([q], padding=True, return_tensors="pt", return_offsets_mapping=True, add_special_tokens=False), n=20)
    print(f"spec_from_file={t:.2f}ms exec_module={e:.2f}ms AutoConfig_cached={ac:.2f}ms template={tb:.2f}ms tokenize={tk:.2f}ms")


if __name__ == "__main__":
    main()
