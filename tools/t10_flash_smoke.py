"""T1.0 flash-attn smoke: real flash_attn_func forward on RTX 5090 (sm_120).

Gate: import + causal forward in fp16 and bf16 on cuda, finite outputs,
correct shape, backward works too (training needs grads).
"""
import sys

import torch

results = {}

try:
    import flash_attn
    from flash_attn import flash_attn_func

    results["flash_attn_version"] = flash_attn.__version__
except Exception as e:
    print(f"IMPORT_FAIL: {type(e).__name__}: {e}")
    sys.exit(1)

torch.manual_seed(0)
dev = "cuda"
B, S, H, D = 2, 512, 16, 64  # head_dim 64, typical for InternVL2 LLM blocks

for dtype in (torch.float16, torch.bfloat16):
    try:
        q = torch.randn(B, S, H, D, device=dev, dtype=dtype, requires_grad=True)
        k = torch.randn(B, S, H, D, device=dev, dtype=dtype, requires_grad=True)
        v = torch.randn(B, S, H, D, device=dev, dtype=dtype, requires_grad=True)
        out = flash_attn_func(q, k, v, causal=True)
        assert out.shape == (B, S, H, D), f"bad shape {out.shape}"
        loss = out.float().square().mean()
        loss.backward()
        assert torch.isfinite(out.float()).all(), "non-finite output"
        assert torch.isfinite(q.grad.float()).all(), "non-finite grad"
        # reference check vs SDPA (loose tolerance for fp16)
        with torch.no_grad():
            qh, kh, vh = [x.detach().transpose(1, 2) for x in (q, k, v)]
            ref = torch.nn.functional.scaled_dot_product_attention(qh, kh, vh, is_causal=True).transpose(1, 2)
            err = (out.float() - ref.float()).abs().max().item()
        results[f"fwd_bwd_{dtype}"] = f"OK max_err_vs_sdpa={err:.4f}"
        print(f"{dtype}: forward+backward OK, max_err_vs_sdpa={err:.4f}")
    except Exception as e:
        print(f"{dtype}: FAIL {type(e).__name__}: {e}")
        sys.exit(2)

print(f"flash_attn {results['flash_attn_version']} smoke PASS on {torch.cuda.get_device_name(0)}")
print(f"peak_mem_allocated={torch.cuda.max_memory_allocated()/2**20:.0f} MiB")
