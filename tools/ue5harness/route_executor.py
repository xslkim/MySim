#!/usr/bin/env python3
"""route_executor.py — UE5 闭环 route 执行器（T2.1）。

功能:
- 解析对齐路线 XML,spawn ego vehicle,同步模式运行,TM autopilot 或 socket agent 控制。
- 实时采集 tick 原始记录(碰撞/交通灯/车道/车速/时间戳),供 scoring.py 计算 DS/SR。
- agent socket 接口:JSON over TCP,payload 含 RGB/车速/next-2 目标点,超时/心跳机制。

用法:
  PYTHONPATH=/home/xsl/MySim/tools conda run -n mysim-ue5 python tools/ue5harness/route_executor.py \
    --routes data/routes/ue5_aligned_routes.xml --route-id 10000 --out logs/t21-smoke
"""
import argparse
import json
import math
import os
import socket
import sys
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple

sys.path.insert(0, "/home/xsl/MySim/tools")
import server_watchdog as w


def host_ip():
    return w.host_ip()


# ========== 数据结构 ==========

@dataclass
class TickRecord:
    """单 tick 原始记录（scoring_core 输入）。"""
    tick: int
    timestamp: float
    sim_time: float
    ego_location: Tuple[float, float, float]
    ego_velocity: Tuple[float, float, float]
    ego_speed: float  # m/s
    ego_acceleration: Tuple[float, float, float]
    collision_impulse: Optional[float] = None  # 碰撞冲量,无碰撞为 None
    collision_actor: Optional[str] = None
    traffic_light_state: Optional[str] = None  # Red/Yellow/Green/Off/Unknown
    traffic_light_id: Optional[int] = None
    lane_id: Optional[int] = None
    road_id: Optional[int] = None
    is_junction: bool = False
    route_completion: float = 0.0  # 0-100
    control: dict = field(default_factory=dict)  # throttle/brake/steer


@dataclass
class RouteConfig:
    route_id: int
    town: str
    keypoints: List[Tuple[float, float, float]]
    weathers: list


@dataclass
class RouteResult:
    route_id: int
    status: str  # Completed / Failed - xxx / Crashed
    route_length: float
    duration_game: float
    duration_system: float
    score_route: float = 0.0
    score_penalty: float = 1.0
    score_composed: float = 0.0
    infractions: dict = field(default_factory=dict)
    ticks: List[TickRecord] = field(default_factory=list)


# ========== 路线解析 ==========

def parse_routes_xml(xml_path: str) -> List[RouteConfig]:
    """解析 Bench2Drive 兼容路线 XML。"""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    routes = []
    for route in root.iter("route"):
        route_id = int(route.attrib["id"])
        town = route.attrib["town"]
        keypoints = []
        for pos in route.find("waypoints").iter("position"):
            keypoints.append((
                float(pos.attrib["x"]),
                float(pos.attrib["y"]),
                float(pos.attrib["z"]),
            ))
        weathers = []
        weathers_elem = route.find("weathers")
        if weathers_elem is not None:
            for w_elem in weathers_elem.iter("weather"):
                weathers.append(dict(w_elem.attrib))
        routes.append(RouteConfig(route_id, town, keypoints, weathers))
    return routes


# ========== Agent Socket 接口 ==========

class AgentSocketServer:
    """JSON over TCP socket server,与模型 agent 通信。

    协议:
    - harness 每 tick 发送: {"tick": int, "rgb": bytes(b64), "speed": float, "target_points": [[x,y],[x,y]], "timestamp": float}
    - agent 回复: {"throttle": float, "brake": float, "steer": float}
    - 心跳: harness 每 N tick 发送 {"heartbeat": true},agent 回复 {"alive": true}
    """

    def __init__(self, host="127.0.0.1", port=5555, timeout=2.0, max_timeouts=3):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.max_timeouts = max_timeouts
        self.server = None
        self.client = None
        self.running = False
        self.timeout_count = 0
        self.last_heartbeat = time.time()

    def start(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((self.host, self.port))
        self.server.listen(1)
        self.server.settimeout(5.0)
        self.running = True
        print(f"[socket] 监听 {self.host}:{self.port}", flush=True)

    def wait_for_agent(self, timeout=30.0):
        """等待 agent 连接,超时返回 False。"""
        if not self.server:
            return False
        self.server.settimeout(timeout)
        try:
            self.client, addr = self.server.accept()
            self.client.settimeout(self.timeout)
            print(f"[socket] agent 已连接: {addr}", flush=True)
            return True
        except socket.timeout:
            print(f"[socket] 等待 agent 超时({timeout}s)", flush=True)
            return False

    def send_tick(self, payload: dict) -> Optional[dict]:
        """发送 tick 数据并等待控制回复。超时返回 None。"""
        if not self.client:
            return None
        try:
            data = json.dumps(payload).encode("utf-8") + b"\n"
            self.client.sendall(data)
            # 读取回复(按行)
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = self.client.recv(4096)
                if not chunk:
                    return None
                buf += chunk
            reply = json.loads(buf.decode("utf-8").strip())
            self.timeout_count = 0
            return reply
        except socket.timeout:
            self.timeout_count += 1
            print(f"[socket] 推理超时({self.timeout_count}/{self.max_timeouts})", flush=True)
            if self.timeout_count >= self.max_timeouts:
                raise RuntimeError(f"agent 连续 {self.max_timeouts} 次超时,fail-fast")
            return None
        except Exception as e:
            print(f"[socket] 通信错误: {e}", flush=True)
            return None

    def stop(self):
        self.running = False
        if self.client:
            self.client.close()
        if self.server:
            self.server.close()


# ========== Route 执行器 ==========

class RouteExecutor:
    def __init__(self, args):
        self.args = args
        self.client = None
        self.world = None
        self.tmap = None
        self.ego = None
        self.sensors = []
        self.route = None  # 稠密化后的路线 [(waypoint, road_option), ...]
        self.route_length = 0.0
        self.traveled_distance = 0.0
        self.last_location = None
        self.start_time = None
        self.start_sim_time = None
        self.tick_count = 0
        self.tick_records: List[TickRecord] = []
        self.collision_sensor = None
        self.lane_invasion_sensor = None
        self.latest_collision = None
        self.latest_lane_invasion = None
        self.socket_server = None
        self.agent_connected = False
        self.tm = None

    def connect(self):
        """连接 UE5 server 并设置同步模式。"""
        import carla
        host = host_ip()
        port = self.args.port
        print(f"[executor] 连接 {host}:{port}", flush=True)
        self.client = carla.Client(host, port)
        self.client.set_timeout(30.0)
        self.world = self.client.get_world()
        self.tmap = self.world.get_map()

        # 同步模式
        settings = self.world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = self.args.dt
        self.world.apply_settings(settings)

        # TM 同步
        self.tm = self.client.get_trafficmanager(self.args.tm_port)
        self.tm.set_synchronous_mode(True)

        print(f"[executor] 同步模式 dt={self.args.dt}, TM port={self.args.tm_port}", flush=True)

    def setup_route(self, route_config: RouteConfig):
        """设置路线:规划路径、spawn ego、挂载传感器。"""
        import carla
        from agents.navigation.global_route_planner import GlobalRoutePlanner

        # 确保地图正确
        current_map = self.tmap.name.split("/")[-1]
        if current_map != route_config.town:
            print(f"[executor] 切换地图 {current_map} → {route_config.town}", flush=True)
            self.world = self.client.load_world(route_config.town)
            self.tmap = self.world.get_map()
            settings = self.world.get_settings()
            settings.synchronous_mode = True
            settings.fixed_delta_seconds = self.args.dt
            self.world.apply_settings(settings)
            self.tm = self.client.get_trafficmanager(self.args.tm_port)
            self.tm.set_synchronous_mode(True)

        # 直接使用 XML 中的完整 waypoints,不再重新规划(避免路径漂移)
        self.route = []
        for kp in route_config.keypoints:
            loc = carla.Location(*kp)
            wp = self.tmap.get_waypoint(loc)
            if wp is None:
                # 若 waypoint 获取失败,用最近的 spawn 点 waypoint
                spawn_points = self.tmap.get_spawn_points()
                if spawn_points:
                    nearest = min(spawn_points, key=lambda sp: sp.location.distance(loc))
                    wp = self.tmap.get_waypoint(nearest.location)
            if wp is None:
                raise RuntimeError(f"无法获取 waypoint at {loc}")
            self.route.append((wp, None))  # road_option 占位,执行器不用

        if len(self.route) < 2:
            raise RuntimeError("路线太短")

        self.route_length = sum(
            self.route[i][0].transform.location.distance(self.route[i + 1][0].transform.location)
            for i in range(len(self.route) - 1)
        )
        print(f"[executor] 路线 {route_config.route_id} 长度 {self.route_length:.1f}m, {len(self.route)} waypoints", flush=True)

        # spawn ego vehicle
        spawn_transform = self.route[0][0].transform
        spawn_transform.location.z += 0.5
        blueprint = self.world.get_blueprint_library().find(self.args.vehicle)
        if blueprint.has_attribute("role_name"):
            blueprint.set_attribute("role_name", "hero")
        self.ego = self.world.spawn_actor(blueprint, spawn_transform)
        print(f"[executor] spawn ego id={self.ego.id} at {spawn_transform.location}", flush=True)

        # 挂载传感器
        self._setup_sensors()

        # 设置天气
        if route_config.weathers:
            w0 = route_config.weathers[0]
            weather = carla.WeatherParameters(
                cloudiness=float(w0.get("cloudiness", 5.0)),
                fog_density=float(w0.get("fog_density", 10.0)),
                precipitation=float(w0.get("precipitation", 0.0)),
                precipitation_deposits=float(w0.get("precipitation_deposits", 0.0)),
                sun_altitude_angle=float(w0.get("sun_altitude_angle", 45.0)),
                sun_azimuth_angle=float(w0.get("sun_azimuth_angle", -1.0)),
                wetness=float(w0.get("wetness", 0.0)),
                wind_intensity=float(w0.get("wind_intensity", 10.0)),
            )
            self.world.set_weather(weather)

    def _setup_sensors(self):
        """挂载碰撞/车道入侵传感器。"""
        import carla

        # 碰撞传感器
        bp = self.world.get_blueprint_library().find("sensor.other.collision")
        self.collision_sensor = self.world.spawn_actor(bp, carla.Transform(), attach_to=self.ego)
        self.collision_sensor.listen(self._on_collision)
        self.sensors.append(self.collision_sensor)

        # 车道入侵传感器
        bp = self.world.get_blueprint_library().find("sensor.other.lane_invasion")
        self.lane_invasion_sensor = self.world.spawn_actor(bp, carla.Transform(), attach_to=self.ego)
        self.lane_invasion_sensor.listen(self._on_lane_invasion)
        self.sensors.append(self.lane_invasion_sensor)

    def _on_collision(self, event):
        self.latest_collision = {
            "impulse": event.normal_impulse.length(),
            "actor": str(event.other_actor.type_id) if event.other_actor else "unknown",
        }

    def _on_lane_invasion(self, event):
        self.latest_lane_invasion = {
            "lane_markings": [str(m.type) for m in event.crossed_lane_markings],
        }

    def _get_traffic_light_state(self):
        """获取自车当前受影响的交通灯状态。"""
        if not self.ego:
            return None, None
        try:
            tl = self.ego.get_traffic_light()
            if tl is not None:
                return str(tl.get_state()), tl.id
        except Exception:
            pass
        return None, None

    def _get_route_progress(self):
        """计算路线完成度(0-100)。"""
        if not self.ego or not self.route:
            return 0.0
        current_loc = self.ego.get_location()
        if self.last_location:
            self.traveled_distance += current_loc.distance(self.last_location)
        self.last_location = current_loc
        return min(100.0, self.traveled_distance / self.route_length * 100.0)

    def _get_next_target_points(self, n=2, lookahead=5.0):
        """获取路线上前方 n 个目标点(间隔 lookahead 米)。"""
        if not self.ego or not self.route:
            return [[0.0, 0.0]] * n
        current_loc = self.ego.get_location()
        # 找最近 waypoint
        min_idx = 0
        min_dist = float("inf")
        for i, (wp, _) in enumerate(self.route):
            d = current_loc.distance(wp.transform.location)
            if d < min_dist:
                min_dist = d
                min_idx = i
        targets = []
        acc = 0.0
        for i in range(min_idx, len(self.route) - 1):
            loc = self.route[i][0].transform.location
            next_loc = self.route[i + 1][0].transform.location
            acc += loc.distance(next_loc)
            if acc >= lookahead * (len(targets) + 1):
                targets.append([next_loc.x, next_loc.y])
                if len(targets) >= n:
                    break
        while len(targets) < n:
            targets.append([self.route[-1][0].transform.location.x, self.route[-1][0].transform.location.y])
        return targets

    def run_route(self, route_config: RouteConfig, max_game_time=200.0):
        """运行单条路线,返回 RouteResult。"""
        import carla

        self.setup_route(route_config)
        self.start_time = time.time()
        self.start_sim_time = self.world.get_snapshot().timestamp.elapsed_seconds
        self.tick_count = 0
        self.tick_records = []
        self.traveled_distance = 0.0
        self.last_location = None

        # autopilot 或 socket agent
        use_socket = self.args.use_socket_agent
        if use_socket:
            self.socket_server = AgentSocketServer(port=self.args.agent_port)
            self.socket_server.start()
            if not self.socket_server.wait_for_agent(timeout=60.0):
                print("[executor] 无 agent 连接,回退 TM autopilot", flush=True)
                use_socket = False
            else:
                self.agent_connected = True

        if not use_socket:
            # TM autopilot 模式
            self.ego.set_autopilot(True, self.args.tm_port)
            # 设置 TM 跟随路线(通过设置目标点序列)
            # 注意:TM autopilot 不直接支持给定路线,这里依赖 TM 的默认行为
            # 如需严格路线跟随,应使用 BasicAgent;T2.4 trivial agent 验证基建即可
            self.tm.ignore_lights_percentage(self.ego, 0.0)
            self.tm.ignore_signs_percentage(self.ego, 0.0)

        result = RouteResult(
            route_id=route_config.route_id,
            status="Started",
            route_length=self.route_length,
            duration_game=0.0,
            duration_system=0.0,
        )

        print(f"[executor] 路线 {route_config.route_id} 开始,最大时长 {max_game_time}s", flush=True)

        while True:
            self.world.tick()
            self.tick_count += 1
            snapshot = self.world.get_snapshot()
            sim_time = snapshot.timestamp.elapsed_seconds - self.start_sim_time

            if not self.ego or not self.ego.is_alive:
                result.status = "Crashed"
                break

            # 收集 tick 数据
            velocity = self.ego.get_velocity()
            speed = math.sqrt(velocity.x ** 2 + velocity.y ** 2 + velocity.z ** 2)
            acceleration = self.ego.get_acceleration()
            control = self.ego.get_control()

            tl_state, tl_id = self._get_traffic_light_state()
            waypoint = self.tmap.get_waypoint(self.ego.get_location())

            record = TickRecord(
                tick=self.tick_count,
                timestamp=time.time(),
                sim_time=sim_time,
                ego_location=(self.ego.get_location().x, self.ego.get_location().y, self.ego.get_location().z),
                ego_velocity=(velocity.x, velocity.y, velocity.z),
                ego_speed=speed,
                ego_acceleration=(acceleration.x, acceleration.y, acceleration.z),
                collision_impulse=self.latest_collision["impulse"] if self.latest_collision else None,
                collision_actor=self.latest_collision["actor"] if self.latest_collision else None,
                traffic_light_state=tl_state,
                traffic_light_id=tl_id,
                lane_id=waypoint.lane_id if waypoint else None,
                road_id=waypoint.road_id if waypoint else None,
                is_junction=waypoint.is_junction if waypoint else False,
                route_completion=self._get_route_progress(),
                control={"throttle": control.throttle, "brake": control.brake, "steer": control.steer},
            )
            self.tick_records.append(record)

            # socket agent 控制
            if use_socket and self.agent_connected:
                payload = {
                    "tick": self.tick_count,
                    "speed": speed,
                    "target_points": self._get_next_target_points(n=2),
                    "timestamp": record.timestamp,
                }
                try:
                    reply = self.socket_server.send_tick(payload)
                    if reply:
                        control = carla.VehicleControl(
                            throttle=float(reply.get("throttle", 0.0)),
                            brake=float(reply.get("brake", 0.0)),
                            steer=float(reply.get("steer", 0.0)),
                        )
                        self.ego.apply_control(control)
                except RuntimeError as e:
                    print(f"[executor] agent 超时 fail-fast: {e}", flush=True)
                    result.status = f"Failed - {e}"
                    break

            # 清除一次性事件
            self.latest_collision = None
            self.latest_lane_invasion = None

            # 终止条件
            if record.route_completion >= 99.0:
                # 到达终点时强制 completion=100,避免 99.x 影响 DS 计算
                record.route_completion = 100.0
                self.tick_records[-1] = record
                result.status = "Completed"
                break
            if sim_time > max_game_time:
                result.status = "Failed - Route timeout"
                break

        result.duration_game = sim_time
        result.duration_system = time.time() - self.start_time
        result.ticks = self.tick_records

        print(f"[executor] 路线 {route_config.route_id} 结束: {result.status}, "
              f"game_time={result.duration_game:.1f}s, completion={record.route_completion:.1f}%", flush=True)

        return result

    def cleanup(self):
        """销毁 actor,恢复异步模式。"""
        if self.socket_server:
            self.socket_server.stop()
        for sensor in self.sensors:
            if sensor and sensor.is_alive:
                sensor.stop()
                sensor.destroy()
        if self.ego and self.ego.is_alive:
            self.ego.destroy()
        if self.world:
            settings = self.world.get_settings()
            settings.synchronous_mode = False
            self.world.apply_settings(settings)
        print("[executor] 清理完成", flush=True)


def save_result(result: RouteResult, out_dir: str):
    """保存路线结果(不含 ticks,避免文件过大;ticks 另存)。"""
    os.makedirs(out_dir, exist_ok=True)
    result_path = os.path.join(out_dir, f"route_{result.route_id}_result.json")
    data = asdict(result)
    ticks = data.pop("ticks")
    with open(result_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    ticks_path = os.path.join(out_dir, f"route_{result.route_id}_ticks.json")
    with open(ticks_path, "w") as f:
        json.dump(ticks, f, indent=2, ensure_ascii=False)
    print(f"[executor] 结果保存 {result_path} / {ticks_path}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--routes", required=True, help="路线 XML 路径")
    ap.add_argument("--route-id", type=int, default=None, help="单条路线 ID(不指定则跑全部)")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--port", type=int, default=2021, help="CARLA server 端口")
    ap.add_argument("--tm-port", type=int, default=8000, help="TM 端口")
    ap.add_argument("--dt", type=float, default=0.05, help="fixed_delta_seconds")
    ap.add_argument("--vehicle", default="vehicle.lincoln.mkz", help="ego 车型")
    ap.add_argument("--max-game-time", type=float, default=200.0, help="单条路线最大 game time")
    ap.add_argument("--use-socket-agent", action="store_true", help="使用 socket agent 而非 TM autopilot")
    ap.add_argument("--agent-port", type=int, default=5555, help="agent socket 端口")
    args = ap.parse_args()

    routes = parse_routes_xml(args.routes)
    if args.route_id is not None:
        routes = [r for r in routes if r.route_id == args.route_id]
        if not routes:
            print(f"[executor] 未找到 route_id={args.route_id}", flush=True)
            sys.exit(1)

    executor = RouteExecutor(args)
    try:
        executor.connect()
        for route_config in routes:
            result = executor.run_route(route_config, max_game_time=args.max_game_time)
            save_result(result, args.out)
    finally:
        executor.cleanup()


if __name__ == "__main__":
    main()
