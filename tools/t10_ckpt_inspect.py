"""Inspect SimLingo official ckpt: key groups, dtypes, total params."""
import sys
from collections import Counter

import torch

CKPT = "/home/xsl/MySim/data/checkpoints/simlingo/pytorch_model.pt"
sd = torch.load(CKPT, map_location="cpu", weights_only=True)
print(f"top-level type: {type(sd)}")
if isinstance(sd, dict) and "state_dict" in sd:
    sd = sd["state_dict"]
    print("unwrapped 'state_dict'")

n = len(sd)
dtypes = Counter(str(v.dtype) for v in sd.values() if isinstance(v, torch.Tensor))
total = sum(v.numel() for v in sd.values() if isinstance(v, torch.Tensor))
print(f"keys: {n}, total params: {total/1e6:.1f}M, dtypes: {dict(dtypes)}")

# group by first 2-3 segments
groups = Counter(".".join(k.split(".")[:3]) for k in sd)
print("\ntop-level groups:")
for g, c in sorted(groups.items()):
    print(f"  {c:6d}  {g}")

print("\nsample keys per major module:")
for pat in ["vision_model.image_encoder.model.vision_model", "vision_model.image_encoder.model.mlp1",
            "language_model.model", "adaptors", "wp_encoder"]:
    ks = [k for k in sd if k.startswith(pat)]
    print(f"  [{pat}] {len(ks)} keys; first: {ks[:2]}")

# any vision-side language_model leftovers?
leftover = [k for k in sd if k.startswith("vision_model") and "language_model" in k]
print(f"\nvision-side language_model keys: {len(leftover)} {leftover[:3]}")
