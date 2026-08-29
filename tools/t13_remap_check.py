# tools/t13_remap_check.py — T1.3 诊断:验证 transfuser_proj→bev_encoder_proj 重映射补丁。
# 用仅含 bev_encoder_proj 的 Tiny 模型跑真 loader(流式,只读 header+2 个 tensor,秒级)。
# 用法:conda run --no-capture-output -n mysim-automot python3 tools/t13_remap_check.py
import sys

import torch
import torch.nn as nn

sys.path.insert(0, "/home/xsl/MySim/external/AutoMoT/leaderboard/team_code")
from automot_utils import load_safetensors_weights_streaming  # noqa: E402


class Tiny(nn.Module):
    def __init__(self):
        super().__init__()
        self.bev_encoder_proj = nn.Linear(1512, 2560, bias=True)


m = Tiny().to(torch.bfloat16)
before = m.bev_encoder_proj.weight.detach().clone()
missing, unexpected = load_safetensors_weights_streaming(m, "/home/xsl/MySim/data/checkpoints/automot")
print("missing:", missing)
print("unexpected count:", len(unexpected), "(Tiny 模型下其余 key 均为 unexpected,正常)")
print("transfuser_proj leaked to unexpected?", any("transfuser" in k for k in unexpected))
print("weight changed by ckpt:", not torch.equal(before, m.bev_encoder_proj.weight))

from safetensors import safe_open  # noqa: E402

with safe_open("/home/xsl/MySim/data/checkpoints/automot/model.safetensors", "pt") as f:
    ref_w = f.get_tensor("transfuser_proj.weight")
    ref_b = f.get_tensor("transfuser_proj.bias")
print("weight == transfuser_proj.weight:", torch.equal(ref_w, m.bev_encoder_proj.weight))
print("bias   == transfuser_proj.bias:  ", torch.equal(ref_b, m.bev_encoder_proj.bias))
