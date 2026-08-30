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

## 巡检记录
- 00:14 巡检①:AutoMoT 220 正常(0.107×,首条路线在跑,server 2031 健康);无处置;下一班 00:43
- 00:43 巡检②:正常(1/220 完成,1711 blocked DS=18.5;第 2 条在跑,日志新鲜);无处置
- 01:13 巡检③:正常(4/220,最近 1792 DS=100;日志 0s 新鲜);无处置
- 01:43 巡检④:正常(5/220 meanDS=40.0,样本太早无意义;日志新鲜);无处置
- 02:13 巡检⑤:正常(6/220 meanDS=37.7);无处置
- 02:43 巡检⑥:正常(7/220 meanDS=35.6,早期样本偏失败路线,持续观察);无处置
- 03:13 巡检⑦:正常(7/220,第 8 条为 Town12 长路线已跑 ~30min,日志实时写入非卡死);无处置
- 03:43 巡检⑧:正常(8/220 meanDS=31.4,第 9 条在跑);无处置
- 04:13 巡检⑨:正常(10/220 meanDS=33.7);无处置
- 04:43 巡检⑩:正常(11/220 meanDS=33.0);无处置
- 05:13 巡检⑪:正常(12/220 meanDS=32.5);无处置
- 05:43/06:13 巡检⑫⑬合并:正常(14/220 meanDS=30.3,日志 80s 前写入属帧间正常);无处置
- 06:43 巡检⑭:正常(16/220 meanDS=28.6);无处置
- 07:14 巡检⑮:**异常处置**——AutoMoT 18/220 时 meanDS=27.5(官方 87.34),14/18 失败签名系统性爬行(TickRuntime RC 35–58%);已停 220 全量+看门狗,server 收编(GPU 回 1.5GB),派 agent-23 诊断(权重装载完整性/控制链路/双专家开关/传感器配置/ckpt 代际);下一步:据诊断结论修复后重冒烟再决定是否重启 220
- 07:43 巡检⑯:正常——诊断 agent-23 活跃(GPU 19.5GB,已出 logs/t13-smoke3-fix1 修复验证冒烟在跑);无处置
- 08:05 处置闭环:**AutoMoT 根因坐实并修复**——ckpt 跨代际改名 transfuser_proj→bev_encoder_proj,单层随机初始化致 BEV token 全垃圾;补丁 _CKPT_KEY_RENAMES(automot_utils.py),冒烟三线 DS 25/59/13→全 100;作废数据归档 logs/t13-full220-broken-bev*;**220 全量 v2 已重启(bash-yzmib7l2 + 看门狗 bash-7g510xjp),装载确认 0 missing/0 unexpected**;AGENTS.md 坑录 +1
- 08:13 巡检⑰:正常——**v2 修复在全量生效:3/220 全 DS=100**(对照 v1 同期 3 条 meanDS≈27);无处置
- 08:43 巡检⑱:正常(6/220 meanDS=93.3 全 Completed);无处置
- 09:13 巡检⑲:正常(10/220 meanDS=96.0);无处置
