#!/usr/bin/env python3
"""T1.1 接线 import 链验证(不连 server,不加载权重)。
PYTHONPATH 由 tools/run_eval_ue4.sh 同款范式传入。逐条报错即修。"""
import os, sys, traceback

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("WANDB_MODE", "offline")
os.environ.setdefault("SAVE_PATH", "/tmp/t11_import_test/")  # agent_wrapper 的 IS_BENCH2DRIVE 开关

ok, fail = 0, 0

def t(name, fn):
    global ok, fail
    try:
        fn()
        ok += 1
        print(f"OK   {name}", flush=True)
    except Exception:
        fail += 1
        print(f"FAIL {name}", flush=True)
        traceback.print_exc()

import numpy as np
print("numpy", np.__version__)

t("shapely.geometry+affinity", lambda: (__import__("shapely.geometry"), __import__("shapely.affinity")))
t("py_trees 0.8", lambda: __import__("py_trees"))
t("dictor/tabulate/ephem/simple_watchdog_timer", lambda: (__import__("dictor"), __import__("tabulate"), __import__("ephem"), __import__("simple_watchdog_timer")))
t("carla pip pkg", lambda: __import__("carla"))
t("agents.navigation(0915 PythonAPI)", lambda: __import__("agents.navigation.global_route_planner", fromlist=["x"]))
t("srunner.scenariomanager.carla_data_provider", lambda: __import__("srunner.scenariomanager.carla_data_provider", fromlist=["x"]))
t("srunner.scenarios(44 type 抽样)", lambda: (__import__("srunner.scenarios.background_activity", fromlist=["x"]), __import__("srunner.scenarios.route_scenario", fromlist=["x"])))
t("leaderboard.utils.route_parser", lambda: __import__("leaderboard.utils.route_parser", fromlist=["x"]))
t("leaderboard.utils.statistics_manager", lambda: __import__("leaderboard.utils.statistics_manager", fromlist=["x"]))
t("leaderboard.autoagents.agent_wrapper", lambda: __import__("leaderboard.autoagents.agent_wrapper", fromlist=["x"]))
t("leaderboard.scenarios.route_scenario", lambda: __import__("leaderboard.scenarios.route_scenario", fromlist=["x"]))
t("leaderboard_evaluator 模块", lambda: __import__("leaderboard.leaderboard_evaluator", fromlist=["x"]))
t("team_code.config_simlingo", lambda: __import__("team_code.config_simlingo", fromlist=["x"]))
t("scenario_logger(top-level)", lambda: __import__("scenario_logger"))
t("filterpy UKF", lambda: __import__("filterpy.kalman", fromlist=["UnscentedKalmanFilter"]))
t("simlingo_training.utils.custom_types", lambda: __import__("simlingo_training.utils.custom_types", fromlist=["x"]))

# agent 模块本体(leaderboard 用 importlib 按文件路径加载,这里直接按路径加载同路径验证)
def _load_agent():
    import importlib.util
    p = "/home/xsl/MySim/external/simlingo/team_code/agent_simlingo.py"
    spec = importlib.util.spec_from_file_location("agent_simlingo", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.get_entry_point() == "LingoAgent"
t("agent_simlingo.py 按文件加载 + get_entry_point", _load_agent)

# hydra to_absolute_path 未初始化行为(agent tick 里用)
def _hydra_path():
    from hydra.utils import to_absolute_path
    p = to_absolute_path("pretrained/InternVL2-1B")
    print("  to_absolute_path ->", p)
t("hydra to_absolute_path(未初始化)", _hydra_path)

print(f"\n== {ok} OK / {fail} FAIL ==")
sys.exit(1 if fail else 0)
