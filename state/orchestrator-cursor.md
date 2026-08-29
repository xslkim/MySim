# orchestrator 游标(每轮落盘)

- 当前里程碑:**M1 UE4 基线复现**(goal 模式,至 CP1;用户授权全自动)
- 在飞任务:无(GPU 空闲;server 两侧均已收编)
- 已完成(增量):**T1.2 收口 PASS——220 全量 DS=86.18(官方 85.07±0.95 ✓)/ SR=68.2%(官方 67.27±2.11 ✓)/ RC=96.94 / pen=0.886,207/220 Completed,13 条失败清单 logs/t12-220-merged.json**;明细 state/tasks/T1.2.md 阶段 B;guardian 自退,双 server 收编
- 已完成:M0/CP0(git 5245071);T1.0 PASS;T1.1 PASS;T1.3 前置 done;T1.4 CPU 段 PORTED;T1.2 阶段 A done;T1.2b 全链 done(**FASTPATH 采纳:split20 fast DS=94.39 ≥ orig 92.54,wall 2.24×**);全天文档 docs/log/2026-08-28.md;双实例基建 done
- 等待:无
- 下一轮动作:① T1.4 MindDrive GPU 冒烟(GPU 空闲,可随时起)② T1.3 AutoMoT 接线+3 路线冒烟(tools/run_eval_automot_ue4.sh 按 T1.3.md 方案写,补丁 vendored evaluator)③ T1.5 CP1 汇总(T1.2 220 成绩+T1.0/T1.1 证据+13 条失败路线归因,判定 M1 收口)
