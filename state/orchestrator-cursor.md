# orchestrator 游标(每轮落盘)

- 当前里程碑:**M1 UE4 基线复现**(goal 模式,至 CP1;用户授权全自动)
- 在飞任务:
  - bash-q3xdzg85 = **T1.3 AutoMoT 220 全量**(单实例 ue4/2031/TM8000,logs/t13-full220,外推 ~30h;显存峰 19.5GB/侧 → 双实例 39GB 不可行,单实例)
  - bash-j5a3nb91 = t13 停滞看门狗(t12_eval_guardian.sh 已通用化为四元组参数)
  - cron 01M1733Q8R1T0P7ZBMG52ZJ61N = 每 30min 夜间巡检(:13/:43)
- 已完成(增量):**T1.3 冒烟 PASS**(3 路线 rc=0 一次过;0.32–0.43s/帧 ≈ SimLingo FASTPATH;220 外推 ~30h;显存峰 19.5GB;`tools/run_eval_automot_ue4.sh` + vendored evaluator 补丁×2);T1.4 done(GPU 冒烟 PASS,0.34s/帧,14.62GiB);Bench2Drive v0.0.3 钉死核实(README L141 声明 + 基 commit 2645714)
- 已完成:M0/CP0(git 5245071);T1.0 PASS;T1.1 PASS;T1.3 前置 done;T1.4 CPU 段 PORTED;T1.2 阶段 A done;T1.2b 全链 done(**FASTPATH 采纳:split20 fast DS=94.39 ≥ orig 92.54,wall 2.24×**);全天文档 docs/log/2026-08-28.md;双实例基建 done
- 等待:AutoMoT 220 全量(~30h,巡检盯)
- 下一轮动作:① 收 AutoMoT 220 → 对 CP1 判据(87.34 README / 89.42 HF 卡,±3)② T1.5 CP1 汇总(state/CP1-report.md:SimLingo/AutoMoT 双侧分数核对 + 13 条失败路线归因 + v0.0.3 钉死)→ M1 收口 ③ AutoMoT 220 完成后 server 收编
