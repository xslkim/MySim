# orchestrator 游标(每轮落盘)

- 当前里程碑:**M2 UE5 自建闭环基建 —— 收口(CP2 PASS,待用户审)**
- 在飞任务:无(GPU 全空,UE4/UE5 server 均已收编)
- 已完成(增量,M2):T2.3 对齐路线集(20 条×3 seeds,UE4/UE5 双 XML + mapping);T2.1 route 执行器 + socket 协议 v0.1(3 路线冒烟 PASS);T2.2 scoring_core 纯函数模块(单元测试全过,系数集与 Bench2Drive 一致);T2.4 trivial agent 无人值守 60 route-runs 全完成(DS=91.70/SR=91.67%,无 server 崩溃);T2.6 交叉验证(UE4 侧 6 条 Perfect DS=99.25±0.09;官方 leaderboard trivial agent TickRuntime 异常,以单元测试 + 系数集一致性替代严格对拍,限制已声明);T2.5 文档 + CP2 材料落盘
- 已完成:M0/CP0(git 5245071);T1.0/T1.1 PASS;T1.2 阶段 A done;T1.2b 全链 done(FASTPATH 采纳);T1.3 AutoMoT quarter56 收官(DS=89.17/RC=98.89,官方 87.34 口径内);T1.4 done;**M1 收口 CP1 PASS**(state/CP1-report.md)
- 等待:用户审 CP2 报告(state/CP2-report.md)
- 下一轮动作:用户授权后开 **M3 渲染对比与 zero-shot 迁移实验(T3.x)**——依赖 CP1∧CP2 均已满足

## 巡检记录
- M1 阶段(08-30 全天)37 班巡检记录见 git 历史;要点:T1.3 07:14 发现 AutoMoT ckpt 跨代际改名(transfuser_proj→bev_encoder_proj)致 BEV 垃圾,08:05 修复重启;11:1x 用户决策 D16 改跑 quarter56 子集;18:3x 收官 CP1 PASS;巡检 cron 已停(授权期满)
- M2 阶段:无长任务在飞,T2.4 为单批次后台任务(bash-w3tpx770,一次过),未设巡检
