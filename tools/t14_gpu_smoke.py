#!/usr/bin/env python
"""T1.4 MindDrive GPU 前向冒烟:真实推理路径(build→load ckpt→GPU→6 目假图→forward_test)。

复刻 team_code/minddrive_b2d_agent.py 的 run_step 数据装配(不依赖 CARLA/leaderboard):
  随机 (900,1600,3) BGR 假图 × 6 目 → 官方 inference_only_pipeline(含 VQA tokenizer)
  → vendored collate → custom_wrap_fp16_model → model(batch, return_loss=False)。

用法(mysim-minddrive env,GPU 直接可用,切勿设 CUDA_VISIBLE_DEVICES=""):
  python tools/t14_gpu_smoke.py                 # 官方默认 fp32_infer=True 路径
  python tools/t14_gpu_smoke.py --fp16-infer    # 撞 dtype assert 时的回退(背骨/LLM fp16)
  python tools/t14_gpu_smoke.py --frames 5 --warmup 1

llm_path 重指向:脚本侧覆盖 config(不改仓内文件)——cfg.model.tokenizer/lm_head 与
inference_only_pipeline 内所有 tokenizer 项统一指到 data/checkpoints/minddrive/llava-qwen2.5-3b。
"""
import argparse
import copy
import os
import sys
import time

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD = os.path.join(REPO, 'external', 'minddrive')
CKPT_DIR = os.path.join(REPO, 'data', 'checkpoints', 'minddrive')
LLM_DIR = os.path.join(CKPT_DIR, 'llava-qwen2.5-3b')
sys.path.insert(0, MD)  # vendored mmcv/adzoo 以此根解析

CFG_PATH = os.path.join(MD, 'adzoo', 'minddrive', 'configs', 'minddrive_qwen25_3B_infer.py')
MAIN_CKPT = os.path.join(CKPT_DIR, 'minddrive_3b_rltrain.pth')

CAMS = ['CAM_FRONT', 'CAM_FRONT_LEFT', 'CAM_FRONT_RIGHT',
        'CAM_BACK', 'CAM_BACK_LEFT', 'CAM_BACK_RIGHT']

# 以下外参常量逐字拷自 team_code/minddrive_b2d_agent.py setup()
LIDAR2IMG = {
    'CAM_FRONT': np.array([[1.14251841e+03, 8.00000000e+02, 0.00000000e+00, -9.52000000e+02],
                           [0.00000000e+00, 4.50000000e+02, -1.14251841e+03, -8.09704417e+02],
                           [0.00000000e+00, 1.00000000e+00, 0.00000000e+00, -1.19000000e+00],
                           [0.00000000e+00, 0.00000000e+00, 0.00000000e+00, 1.00000000e+00]]),
    'CAM_FRONT_LEFT': np.array([[6.03961325e-14, 1.39475744e+03, 0.00000000e+00, -9.20539908e+02],
                                [-3.68618420e+02, 2.58109396e+02, -1.14251841e+03, -6.47296750e+02],
                                [-8.19152044e-01, 5.73576436e-01, 0.00000000e+00, -8.29094072e-01],
                                [0.00000000e+00, 0.00000000e+00, 0.00000000e+00, 1.00000000e+00]]),
    'CAM_FRONT_RIGHT': np.array([[1.31064327e+03, -4.77035138e+02, 0.00000000e+00, -4.06010608e+02],
                                 [3.68618420e+02, 2.58109396e+02, -1.14251841e+03, -6.47296750e+02],
                                 [8.19152044e-01, 5.73576436e-01, 0.00000000e+00, -8.29094072e-01],
                                 [0.00000000e+00, 0.00000000e+00, 0.00000000e+00, 1.00000000e+00]]),
    'CAM_BACK': np.array([[-5.60166031e+02, -8.00000000e+02, 0.00000000e+00, -1.28800000e+03],
                          [5.51091060e-14, -4.50000000e+02, -5.60166031e+02, -8.58939847e+02],
                          [1.22464680e-16, -1.00000000e+00, 0.00000000e+00, -1.61000000e+00],
                          [0.00000000e+00, 0.00000000e+00, 0.00000000e+00, 1.00000000e+00]]),
    'CAM_BACK_LEFT': np.array([[-1.14251841e+03, 8.00000000e+02, 0.00000000e+00, -6.84385123e+02],
                               [-4.22861679e+02, -1.53909064e+02, -1.14251841e+03, -4.96004706e+02],
                               [-9.39692621e-01, -3.42020143e-01, 0.00000000e+00, -4.92889531e-01],
                               [0.00000000e+00, 0.00000000e+00, 0.00000000e+00, 1.00000000e+00]]),
    'CAM_BACK_RIGHT': np.array([[3.60989788e+02, -1.34723223e+03, 0.00000000e+00, -1.04238127e+02],
                                [4.22861679e+02, -1.53909064e+02, -1.14251841e+03, -4.96004706e+02],
                                [9.39692621e-01, -3.42020143e-01, 0.00000000e+00, -4.92889531e-01],
                                [0.00000000e+00, 0.00000000e+00, 0.00000000e+00, 1.00000000e+00]]),
}
LIDAR2CAM = {
    'CAM_FRONT': np.array([[1., 0., 0., 0.],
                           [0., 0., -1., -0.24],
                           [0., 1., 0., -1.19],
                           [0., 0., 0., 1.]]),
    'CAM_FRONT_LEFT': np.array([[0.57357644, 0.81915204, 0., -0.22517331],
                                [0., 0., -1., -0.24],
                                [-0.81915204, 0.57357644, 0., -0.82909407],
                                [0., 0., 0., 1.]]),
    'CAM_FRONT_RIGHT': np.array([[0.57357644, -0.81915204, 0., 0.22517331],
                                 [0., 0., -1., -0.24],
                                 [0.81915204, 0.57357644, 0., -0.82909407],
                                 [0., 0., 0., 1.]]),
    'CAM_BACK': np.array([[-1., 0., 0., 0.],
                          [0., 0., -1., -0.24],
                          [0., -1., 0., -1.61],
                          [0., 0., 0., 1.]]),
    'CAM_BACK_LEFT': np.array([[-0.34202014, 0.93969262, 0., -0.25388956],
                               [0., 0., -1., -0.24],
                               [-0.93969262, -0.34202014, 0., -0.49288953],
                               [0., 0., 0., 1.]]),
    'CAM_BACK_RIGHT': np.array([[-0.34202014, -0.93969262, 0., 0.25388956],
                                [0., 0., -1., -0.24],
                                [0.93969262, -0.34202014, 0., -0.49288953],
                                [0., 0., 0., 1.]]),
}
LIDAR2EGO = np.array([[0., 1., 0., -0.39],
                      [-1., 0., 0., 0.],
                      [0., 0., 1., 1.84],
                      [0., 0., 0., 1.]])

CUSTOM_FP16 = dict(map_head=False, pts_bbox_head=False)  # 同 agent custom_wrap_fp16_model


def custom_wrap_fp16_model(model):
    for m in model.modules():
        if hasattr(m, 'fp16_enabled'):
            m.fp16_enabled = True
    for module_name, v in CUSTOM_FP16.items():
        model._modules[module_name].fp16_enabled = v


def command2hot(command, max_dim=6):
    if command < 0:
        command = 4
    command -= 1
    cmd_one_hot = np.zeros(max_dim)
    cmd_one_hot[command] = 1
    return cmd_one_hot


def command2nohot(command, max_dim=6):
    if command < 0:
        command = 4
    command -= 1
    return command


def invert_matrix_egopose_numpy(egopose):
    inverse_matrix = np.zeros((4, 4), dtype=np.float32)
    rotation = egopose[:3, :3]
    translation = egopose[:3, 3]
    inverse_matrix[:3, :3] = rotation.T
    inverse_matrix[:3, 3] = -np.dot(rotation.T, translation)
    inverse_matrix[3, 3] = 1.0
    return inverse_matrix


def patch_cfg(cfg, fp16_infer):
    """llm_path 重指向 + 推理构建裁枝(脚本侧覆盖,不改仓内 config 文件)。"""
    cfg = cfg.copy()
    cfg.model['tokenizer'] = LLM_DIR
    cfg.model['lm_head'] = LLM_DIR
    cfg.model['train_cfg'] = None  # 推理构建无需 assigner
    if fp16_infer:
        cfg.model['fp32_infer'] = False
        cfg.model['fp16_infer'] = True
    n_tok = 0
    for step in cfg.inference_only_pipeline:
        if 'tokenizer' in step:
            step['tokenizer'] = LLM_DIR
            n_tok += 1
    assert n_tok >= 1, 'inference_only_pipeline 内未找到 tokenizer 项'
    print(f'[OK] config 覆盖: tokenizer/lm_head → {LLM_DIR} (pipeline tokenizer ×{n_tok})'
          + ('; fp16_infer=True' if fp16_infer else '; fp32_infer=True(官方默认)'))
    return cfg


def build_and_load(fp16_infer):
    import torch
    from mmcv import Config
    from mmcv.models import build_model

    cfg = patch_cfg(Config.fromfile(CFG_PATH), fp16_infer)
    t0 = time.time()
    model = build_model(cfg.model)
    n_param = sum(p.numel() for p in model.parameters())
    print(f'[OK] 模型构建 {time.time()-t0:.1f}s: {n_param/1e9:.2f}B 参数')

    # mmap 惰性加载 29.5GB ckpt,避免 WSL 32GB RAM 上限下全量驻留
    t0 = time.time()
    sd = torch.load(MAIN_CKPT, map_location='cpu', mmap=True, weights_only=True)
    if 'state_dict' in sd:
        sd = sd['state_dict']
    incompat = model.load_state_dict(sd, strict=False)
    del sd
    print(f'[OK] ckpt 加载 {time.time()-t0:.1f}s: missing {len(incompat.missing_keys)}, '
          f'unexpected {len(incompat.unexpected_keys)} (预期 0 / ~800, RL value_net+inv_freq)')
    assert len(incompat.missing_keys) == 0, f'missing keys: {incompat.missing_keys[:5]}'

    t0 = time.time()
    model.cuda()
    model.eval()
    torch.cuda.synchronize()
    print(f'[OK] model.cuda() {time.time()-t0:.1f}s; 权重显存 '
          f'{torch.cuda.memory_allocated()/2**30:.2f}GiB')
    return model, cfg


def make_results(step, rng):
    """复刻 agent.run_step 的 results 装配(tick 部分用固定 mock 量)。"""
    from mmcv.core.bbox import get_box_type
    from pyquaternion import Quaternion

    # mock tick 量:静止参考系,直行 LANEFOLLOW,速度 2 m/s
    pos = np.array([0.0, 0.0])
    speed = 2.0
    raw_theta = 0.0
    acceleration = np.zeros(3)
    angular_velocity = np.zeros(3)
    command_curr = 4  # RoadOption.LANEFOLLOW
    command_near_xy = np.array([10.0, 0.0])

    imgs = [rng.integers(0, 256, size=(900, 1600, 3), dtype=np.uint8) for _ in CAMS]

    results = {}
    results['lidar2img'] = np.stack([LIDAR2IMG[c] for c in CAMS], axis=0)
    results['lidar2cam'] = np.stack([LIDAR2CAM[c] for c in CAMS], axis=0)
    results['cam_intrinsic'] = np.stack(
        [np.matmul(LIDAR2IMG[c], np.linalg.inv(LIDAR2CAM[c])) for c in CAMS], axis=0)
    results['img'] = imgs
    results['folder'] = ' '
    results['scene_token'] = ' '
    results['frame_idx'] = step
    results['timestamp'] = step / 20
    results['box_type_3d'], _ = get_box_type('LiDAR')

    ego_theta = -raw_theta + np.pi / 2
    rotation = list(Quaternion(axis=[0, 0, 1], radians=ego_theta))
    can_bus = np.zeros(18)
    can_bus[0] = pos[0]
    can_bus[1] = -pos[1]
    can_bus[3:7] = rotation
    can_bus[7] = speed
    can_bus[10:13] = acceleration
    can_bus[11] *= -1
    can_bus[13:16] = -angular_velocity
    can_bus[16] = ego_theta
    can_bus[17] = ego_theta / np.pi * 180
    results['can_bus'] = can_bus
    results['command'] = command2nohot(command_curr)
    results['ego_fut_cmd'] = command2hot(command_curr)

    ego2world = np.eye(4)
    ego2world[0:3, 0:3] = Quaternion(axis=[0, 0, 1], radians=ego_theta).rotation_matrix
    ego2world[0:2, 3] = can_bus[0:2]
    lidar2global = ego2world @ LIDAR2EGO
    results['ego_pose'] = lidar2global
    results['ego_pose_inv'] = invert_matrix_egopose_numpy(lidar2global)
    results['lidar2ego'] = LIDAR2EGO
    results['l2g_r_mat'] = lidar2global[0:3, 0:3]
    results['l2g_t'] = lidar2global[0:3, 3]

    stacked_imgs = np.stack(results['img'], axis=-1)
    results['img_shape'] = stacked_imgs.shape
    results['ori_shape'] = stacked_imgs.shape
    results['pad_shape'] = stacked_imgs.shape
    return results


def build_pipeline(cfg):
    from mmcv.datasets.pipelines import Compose
    steps = [s for s in cfg.inference_only_pipeline
             if s['type'] not in ['LoadMultiViewImageFromFilesInCeph']]
    return Compose(steps)


def collate_to_device(results, device):
    import torch
    from mmcv.parallel.collate import collate as mm_collate_to_batch_form
    input_data_batch = mm_collate_to_batch_form([results], samples_per_gpu=1)
    # 设备迁移循环逐字拷自 agent.run_step
    for key, data in input_data_batch.items():
        if key != 'img_metas':
            if torch.is_tensor(data[0]):
                data[0] = data[0].to(device)
        if key == 'input_ids':
            for i in range(len(data[0])):
                for k in range(len(data[0][i])):
                    data[0][i][k] = data[0][i][k].to(device)
    return input_data_batch


def check_tensor(name, t):
    import torch
    t = t.detach().float()
    n_nan = torch.isnan(t).sum().item()
    n_inf = torch.isinf(t).sum().item()
    return (f'{name}: shape {tuple(t.shape)} dtype {t.dtype} | '
            f'min {t.min().item():.4f} max {t.max().item():.4f} '
            f'mean {t.mean().item():.4f} | NaN {n_nan} Inf {n_inf}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fp16-infer', action='store_true',
                    help='fp32_infer 撞 dtype assert 时的回退:backbone/LLM fp16')
    ap.add_argument('--frames', type=int, default=5, help='计时帧数(默认 5)')
    ap.add_argument('--warmup', type=int, default=1, help='热身帧数(默认 1)')
    ap.add_argument('--seed', type=int, default=0)
    args = ap.parse_args()

    import torch
    assert torch.cuda.is_available(), 'CUDA 不可用'
    print(f'[env] torch {torch.__version__} | GPU {torch.cuda.get_device_name(0)} | '
          f'空闲显存 {(torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_allocated())/2**30:.1f}GiB')

    model, cfg = build_and_load(args.fp16_infer)
    pipeline = build_pipeline(cfg)
    torch.cuda.reset_peak_memory_stats()

    rng = np.random.default_rng(args.seed)
    prep_times, fwd_times = [], []
    total_frames = args.warmup + args.frames
    with torch.no_grad():
        for step in range(total_frames):
            t0 = time.time()
            results = make_results(step, rng)
            results = pipeline(results)
            batch = collate_to_device(results, 'cuda')
            custom_wrap_fp16_model(model)
            torch.cuda.synchronize()
            t1 = time.time()
            out = model(batch, return_loss=False)
            torch.cuda.synchronize()
            t2 = time.time()
            tag = 'warmup' if step < args.warmup else f'frame{step - args.warmup}'
            prep_times.append(t1 - t0)
            fwd_times.append(t2 - t1)
            pts = out[0]['pts_bbox']
            n_det = pts['boxes_3d'].tensor.shape[0] if 'boxes_3d' in pts else -1
            score_max = pts['scores_3d'].max().item() if n_det and n_det > 0 else float('nan')
            print(f'[{tag}] prep {t1-t0:.2f}s | forward {t2-t1:.2f}s | '
                  f'det {n_det} boxes (score max {score_max:.3f}) | '
                  f'speed_cmd {pts.get("speed_value", "?")} path_cmd {pts.get("path_value", "?")}')
            if step == total_frames - 1:
                print('  ' + check_tensor('ego_fut_preds', pts['ego_fut_preds']))
                if 'pw_ego_fut_pred' in pts:
                    print('  ' + check_tensor('pw_ego_fut_pred', pts['pw_ego_fut_pred']))
                ego = pts['ego_fut_preds'].detach().float()
                pw = pts.get('pw_ego_fut_pred', ego).detach().float()
                assert torch.isfinite(ego).all() and torch.isfinite(pw).all(), 'NaN/Inf in traj!'

    timed = fwd_times[args.warmup:]
    med = float(np.median(timed))
    peak = torch.cuda.max_memory_allocated() / 2**30
    print('\n===== GPU 冒烟小结 =====')
    print(f'路径: {"fp16_infer" if args.fp16_infer else "fp32_infer(官方默认)"}')
    print(f'单帧前向: median {med:.2f}s (min {min(timed):.2f} / max {max(timed):.2f}), '
          f'pipeline+collate 均值 {np.mean(prep_times):.2f}s')
    print(f'显存峰值(torch.max_memory_allocated): {peak:.2f}GiB')
    print('PASS')


if __name__ == '__main__':
    main()
