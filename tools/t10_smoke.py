"""T1.0 SimLingo end-to-end smoke on RTX 5090 (sm_120).

Phases:
  A. Build DrivingModel via hydra from the official release config, load the
     official ckpt with strict=True (must report 0 missing / 0 unexpected keys).
  B. Build a synthetic DrivingExample through the production DataModule
     collate path (real InternVL2 image tiling + chat template).
  C. Inference forward() (greedy language + driving heads) under bf16 autocast.
  D. Single-batch training through pytorch_lightning Trainer (16-mixed, AdamW
     via configure_optimizers) with the production JsonlMetricsLogger callback
     and offline WandbLogger.
  E. Verify train_metrics.jsonl landed with step/loss/lr rows.

Run:  PYTHONPATH=<repo> conda run -n mysim-simlingo python tools/t10_smoke.py --bs 6
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch

os.environ.setdefault("WANDB_MODE", "offline")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

REPO = "/home/xsl/MySim/external/simlingo"
sys.path.insert(0, REPO)
CKPT = "/home/xsl/MySim/data/checkpoints/simlingo/pytorch_model.pt"
HYDRA_CFG = "/home/xsl/MySim/data/checkpoints/simlingo/hydra_config.yaml"


def build_model_and_dm():
    import hydra.utils
    from omegaconf import OmegaConf
    from transformers import AutoProcessor

    cfg = OmegaConf.load(HYDRA_CFG)
    processor = AutoProcessor.from_pretrained(cfg.model.vision_model.variant, trust_remote_code=True)
    dm = hydra.utils.instantiate(
        cfg.data_module,
        processor=processor,
        encoder_variant=cfg.model.vision_model.variant,
        llm_variant=cfg.model.language_model.variant,
        _recursive_=False,
    )
    model = hydra.utils.instantiate(
        cfg.model,
        cfg_data_module=cfg.data_module,
        processor=processor,
        cache_dir=None,
        _recursive_=False,
    )
    return model, dm


def make_item(idx: int):
    from simlingo_training.utils.custom_types import DatasetOutput

    rng = np.random.default_rng(idx)
    image_ff = rng.integers(0, 255, size=(1, 3, 1280, 2048), dtype=np.uint8)  # [T,C,H,W]
    user_text = (
        "Current speed: 3.5 m/s. Target waypoint: (10.0, 0.0). "
        "Command: follow the lane. What should the ego do next?"
    )
    answer_text = "Keep the current speed and follow the lane."
    conversation = [
        {"role": "user", "content": [{"text": user_text}]},
        {"role": "assistant", "content": [{"text": answer_text}]},
    ]
    answer = [{"content": [{"text": answer_text}]}]
    return DatasetOutput(
        conversation=conversation,
        answer=answer,
        image_ff=image_ff,
        image_ff_org_size=(2048, 1280),
        waypoints=[(float(i) * 0.7, 0.05 * i) for i in range(10)],  # dataset stores pred_len+1 sliced [1:-1] -> 10
        waypoints_1d=[(float(i) * 0.7, 0.0) for i in range(10)],
        path=[(float(i) * 2.0, 0.0) for i in range(20)],
        target_points=(10.0, 0.0),
        speed=3.5,
        placeholder_values={},
        measurement_path=f"synthetic/route_{idx}",
        dataset="synthetic",
        qa_templates=None,
        eval_infos=None,
    )


def phase_a(model):
    print("\n=== Phase A: ckpt strict load ===", flush=True)
    sd = torch.load(CKPT, map_location="cpu", weights_only=True)
    try:
        result = model.load_state_dict(sd, strict=True)
        missing, unexpected = list(result.missing_keys), list(result.unexpected_keys)
    except RuntimeError as e:
        msg = str(e)
        missing = [l for l in msg.splitlines() if "Missing" in l]
        unexpected = [l for l in msg.splitlines() if "Unexpected" in l]
        print("STRICT LOAD FAILED:")
        print(msg[:4000])
        return False
    print(f"missing keys: {len(missing)} {missing[:5]}")
    print(f"unexpected keys: {len(unexpected)} {unexpected[:5]}")
    return len(missing) == 0 and len(unexpected) == 0


def phase_c(model, dm, device):
    print("\n=== Phase C: inference forward (synthetic batch, bs=1) ===", flush=True)
    batch = dm.dl_collate_fn([make_item(1000)])
    model = model.to(device)
    model.eval()

    def to_dev(x):
        if isinstance(x, torch.Tensor):
            return x.to(device)
        if isinstance(x, tuple) and hasattr(x, "_fields"):
            return type(x)(*[to_dev(v) for v in x])
        if isinstance(x, list):
            return [to_dev(v) for v in x]
        if isinstance(x, dict):
            return {k: to_dev(v) for k, v in x.items()}
        return x

    batch = to_dev(batch)
    t0 = time.time()
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
        speed_wps, route, language = model.forward(batch)
    dt = time.time() - t0
    assert speed_wps.shape == (1, 10, 2), f"speed_wps shape {speed_wps.shape}"
    assert route.shape == (1, 20, 2), f"route shape {route.shape}"
    assert isinstance(language, list) and len(language) == 1
    for name, t in [("speed_wps", speed_wps), ("route", route)]:
        assert torch.isfinite(t.float()).all(), f"{name} has non-finite values"
    print(f"speed_wps {tuple(speed_wps.shape)} finite OK; route {tuple(route.shape)} finite OK")
    print(f"language[0] = {language[0]!r:.120}")
    print(f"inference forward took {dt:.1f}s (incl. 100-token greedy decode)")
    model.train()
    return True


def phase_d(model, batch, outdir, device):
    print("\n=== Phase D: single-batch training via PL Trainer ===", flush=True)
    import pytorch_lightning as pl
    from pytorch_lightning.loggers import WandbLogger
    from torch.utils.data import DataLoader

    from simlingo_training.callbacks.jsonl_logger import JsonlMetricsLogger

    dl = DataLoader([batch] * 4, batch_size=None, num_workers=0)
    jsonl_path = Path(outdir) / "train_metrics.jsonl"
    wandb_logger = WandbLogger(project="simlingo", name="t10-smoke", save_dir=str(outdir))
    trainer = pl.Trainer(
        accelerator="gpu",
        devices=1,
        max_steps=2,
        precision="16-mixed",
        gradient_clip_val=0.3,
        callbacks=[JsonlMetricsLogger(str(jsonl_path))],
        logger=wandb_logger,
        enable_checkpointing=False,
        enable_model_summary=False,
        num_sanity_val_steps=0,
    )
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    trainer.fit(model, train_dataloaders=dl)
    dt = time.time() - t0
    peak = torch.cuda.max_memory_allocated() / 2**30
    print(f"2 train steps in {dt:.1f}s; peak VRAM {peak:.2f} GiB")
    try:
        import wandb
        wandb.finish()
    except Exception:
        pass

    print("\n=== Phase E: train_metrics.jsonl check ===", flush=True)
    assert jsonl_path.exists(), f"{jsonl_path} missing"
    rows = [json.loads(l) for l in jsonl_path.read_text().splitlines() if l.strip()]
    print(f"{len(rows)} rows; first row keys: {sorted(rows[0].keys())}")
    for r in rows:
        assert "step" in r and "lr" in r, f"missing step/lr in {r}"
    loss_keys = [k for k in rows[0] if "loss" in k]
    assert loss_keys, "no loss field in jsonl rows"
    print(f"loss fields: {loss_keys}; last row: {rows[-1]}")
    return True, peak


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bs", type=int, default=6)
    ap.add_argument("--outdir", default="/home/xsl/MySim/logs/t10-smoke")
    ap.add_argument("--skip-inference", action="store_true")
    args = ap.parse_args()
    Path(args.outdir).mkdir(parents=True, exist_ok=True)
    os.chdir(args.outdir)  # hydra to_absolute_path('pretrained/...') resolves from cwd

    import pytorch_lightning as pl
    pl.seed_everything(0, workers=True)
    device = "cuda"

    t0 = time.time()
    model, dm = build_model_and_dm()
    print(f"model+datamodule built in {time.time()-t0:.1f}s")

    ok_a = phase_a(model)
    if not ok_a:
        print("FAIL: ckpt key mismatch")
        sys.exit(3)

    ok_c = True
    if not args.skip_inference:
        ok_c = phase_c(model, dm, device)

    train_batch = dm.dl_collate_fn([make_item(i) for i in range(args.bs)])
    print(f"train batch collated: bs={args.bs}, "
          f"pixels {tuple(train_batch.driving_input.camera_images.shape)}, "
          f"prompt ids {tuple(train_batch.driving_input.prompt.phrase_ids.shape)}")
    ok_d, peak = phase_d(model, train_batch, args.outdir, device)

    print(f"\nRESULT: ckpt_load={'PASS' if ok_a else 'FAIL'} "
          f"inference={'PASS' if ok_c else 'FAIL'} train_step={'PASS' if ok_d else 'FAIL'} "
          f"peak_vram_gib={peak:.2f}")
    sys.exit(0 if (ok_a and ok_c and ok_d) else 1)


if __name__ == "__main__":
    main()
