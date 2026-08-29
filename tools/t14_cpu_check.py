#!/usr/bin/env python
"""T1.4 MindDrive torch2.7 移植 — CPU 可验证段(import 链 / config 解析 / 模型构建 / ckpt 键匹配)。

不碰 GPU:不分配显存即可;**切勿设 CUDA_VISIBLE_DEVICES=""**——WSL2 下会让
transformers is_flash_attn_2_available()→torch.cuda.is_available() 双 free 崩(driver 577.00+cu128)。
用法:
  python tools/t14_cpu_check.py [--build-model] [--ckpt-keys]

  默认只跑 import 链 + config 解析;--build-model 做 CPU 全量构建(3B fp32 约 14GB RAM,慢);
  --ckpt-keys 用 mmap 惰性读 29.5GB ckpt 比对键(不占满内存)。
"""
import argparse
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD = os.path.join(REPO, 'external', 'minddrive')
CKPT_DIR = os.path.join(REPO, 'data', 'checkpoints', 'minddrive')
LLM_DIR = os.path.join(CKPT_DIR, 'llava-qwen2.5-3b')
sys.path.insert(0, MD)  # vendored mmcv/adzoo 以此根解析(editable install 亦可)

CFG_PATH = os.path.join(MD, 'adzoo', 'minddrive', 'configs', 'minddrive_qwen25_3B_infer.py')
MAIN_CKPT = os.path.join(CKPT_DIR, 'minddrive_3b_rltrain.pth')


def step_imports():
    import mmcv  # noqa: F401  触发 core->post_processing->iou3d_cuda / ops._ext 硬链
    from mmcv.ops.iou3d_det import nms_gpu  # noqa: F401  CUDA 扩展符号可见
    from mmcv.utils.ext_loader import check_ops_exist
    assert check_ops_exist(), 'mmcv._ext 未编译/不可见'
    from mmcv.models import build_model  # noqa: F401
    from mmcv.models.detectors.minddrive import Minddrive  # noqa: F401
    from mmcv.utils.llava_qwen import LlavaQwen2ForCausalLM  # noqa: F401
    print('[OK] import 链全通(mmcv._ext / iou3d_cuda / Minddrive / LlavaQwen2)')


def step_config():
    from mmcv import Config
    cfg = Config.fromfile(CFG_PATH)
    assert cfg.model['type'] == 'Minddrive'
    assert cfg.model['lm_model_type'] == 'qwen25_3B'
    print('[OK] config 解析:', os.path.basename(CFG_PATH),
          '| backbone:', cfg.model['img_backbone']['type'],
          '| head:', cfg.model['pts_bbox_head']['type'])
    return cfg


def step_build(cfg):
    import torch
    from mmcv.models import build_model
    cfg = cfg.copy()
    cfg.model['tokenizer'] = LLM_DIR
    cfg.model['lm_head'] = LLM_DIR
    cfg.model['train_cfg'] = None  # 推理构建无需 assigner
    model = build_model(cfg.model)
    n_param = sum(p.numel() for p in model.parameters())
    print(f'[OK] CPU 模型构建完成: {n_param/1e9:.2f}B 参数, '
          f'fp32 占用 ~{n_param*4/2**30:.1f}GiB')
    return model


def step_ckpt_keys(model=None):
    import torch
    sd = torch.load(MAIN_CKPT, map_location='cpu', mmap=True, weights_only=True)
    if 'state_dict' in sd:
        sd = sd['state_dict']
    ckpt_keys = set(sd.keys())
    print(f'[OK] ckpt 读取(mmap): {len(ckpt_keys)} 键')
    if model is not None:
        ref_keys = set(model.state_dict().keys())
        hit = len(ckpt_keys & ref_keys)
        missing = sorted(ref_keys - ckpt_keys)
        unexpected = sorted(ckpt_keys - ref_keys)
        print(f'[键匹配] 命中 {hit}/{len(ref_keys)}; missing {len(missing)}, unexpected {len(unexpected)}')
        for k in missing[:10]:
            print('  missing:', k)
        for k in unexpected[:10]:
            print('  unexpected:', k)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--build-model', action='store_true')
    ap.add_argument('--ckpt-keys', action='store_true')
    args = ap.parse_args()
    step_imports()
    cfg = step_config()
    model = step_build(cfg) if args.build_model else None
    if args.ckpt_keys:
        step_ckpt_keys(model)
    print('T1.4 CPU 验证段完成')
