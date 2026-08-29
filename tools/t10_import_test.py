"""T1.0 import chain test for simlingo_training (training + inference deps)."""
import sys
import traceback

MODS = [
    # core
    "torch", "torchvision", "numpy", "PIL", "cv2", "scipy", "matplotlib",
    # training framework
    "hydra", "omegaconf", "pytorch_lightning", "torchmetrics", "deepspeed",
    "wandb", "git", "peft", "accelerate", "timm", "einops", "flash_attn",
    "transformers", "tokenizers", "safetensors", "huggingface_hub",
    # dataset / utils
    "imgaug", "shapely", "ujson", "retry", "filterpy", "line_profiler",
    "imageio", "skimage", "carla",
    # repo modules (need WORK_DIR on sys.path)
    "simlingo_training.config",
    "simlingo_training.models.driving",
    "simlingo_training.models.encoder.vlm",
    "simlingo_training.models.encoder.internvl2_model",
    "simlingo_training.models.language_model.llm",
    "simlingo_training.models.adaptors.adaptors",
    "simlingo_training.dataloader.datamodule",
    "simlingo_training.dataloader.dataset_driving",
    "simlingo_training.dataloader.dataset_dreamer",
    "simlingo_training.dataloader.dataset_eval_qa_comm",
    "simlingo_training.dataloader.dataset_eval_dreamer",
    "simlingo_training.callbacks.visualise",
    "simlingo_training.utils.logging_project",
    "simlingo_training.utils.internvl2_utils",
    "simlingo_training.utils.transfuser_utils",
    "simlingo_training.utils.projection",
    "simlingo_training.train",
]

fails = []
for m in MODS:
    try:
        __import__(m)
        print(f"OK   {m}")
    except Exception as e:
        fails.append(m)
        print(f"FAIL {m}: {type(e).__name__}: {e}")
        traceback.print_exc(limit=2)

print(f"\n{len(MODS)-len(fails)}/{len(MODS)} OK")
sys.exit(1 if fails else 0)
