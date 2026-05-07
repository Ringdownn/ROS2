# Catch Turtle All

基于 `turtlesim` 的 ROS2 自动抓海龟 + 链式跟随系统。每 3 秒生成一只海龟，主海龟自动追最近的目标，抓到的海龟依次跟随前一只。

详细方案见 `catch_turtle_implementation_plan.md`，详细编码计划见 `catch_turtle_coding_plan.md`。

## 项目结构

```text
ros2_ws/
└── src/
    ├── catch_turtle_interfaces/      # 接口包：自定义 action（ament_cmake）
    │   ├── action/CatchTarget.action
    │   ├── CMakeLists.txt
    │   └── package.xml
    └── catch_turtle_bringup/         # 主功能包：节点 + launch + 参数（ament_python）
        ├── catch_turtle_bringup/
        │   ├── __init__.py
        │   ├── utils.py
        │   ├── turtle_registry.py
        │   ├── spawn_manager.py
        │   ├── master_manager.py
        │   ├── catch_executor.py
        │   └── follower_manager.py
        ├── launch/catch_turtle.launch.py
        ├── config/params.yaml
        ├── resource/catch_turtle_bringup
        ├── setup.py
        └── package.xml
```

## 包与文件作用

### `catch_turtle_interfaces` —— 只放接口

| 文件 | 作用 |
| --- | --- |
| `action/CatchTarget.action` | 定义"抓海龟"动作：Goal=要抓哪只 / Result=是否抓到、抓到谁 / Feedback=剩余距离。 |
| `CMakeLists.txt` | 声明用 `rosidl_default_generators` 编译 `.action`，生成可被 Python/C++ 调用的类。 |
| `package.xml` | 声明 `ament_cmake` 接口包，加入 `rosidl_interface_packages` 组。 |

### `catch_turtle_bringup` —— 业务节点与运行配置

#### 4 个业务节点

| 文件 | 角色 | 关键职责 |
| --- | --- | --- |
| `spawn_manager.py` | "**生**" | 每 3 秒调 `/spawn` 服务生成新海龟；启动扫描已有 `turtleN` 编号 +1 起步；重名失败自动跳号。 |
| `master_manager.py` | "**想**" | 自动发现 `/turtleN/pose`，每 0.5 秒挑最近目标；运行中持续比较，更近目标超过 `preempt_margin` 就**抢占**当前 goal；失败冷却避免反复抓同一只。 |
| `catch_executor.py` | "**抓**" | Action Server，控制 `turtle1` 去抓；默认动作集 = **前进 / 左转 / 右转**，开启 `allow_reverse` 后追加"后退"，每 tick 在前/后两方向中选误差小的走；单 goal 串行 + 总超时 + 无 pose 超时；用 `MultiThreadedExecutor` + `ReentrantCallbackGroup`。 |
| `follower_manager.py` | "**跟**" | 订阅 `/caught_chain`，让链上每只海龟跟随前一只，向各自 `/turtleN/cmd_vel` 发速度。 |

#### 3 个支撑模块

| 文件 | 作用 |
| --- | --- |
| `__init__.py` | 把目录标为 Python 包，保持空文件。 |
| `utils.py` | 数学工具：`normalize_angle` / `distance` / `angle_to` / `clamp` / `sign`。 |
| `turtle_registry.py` | `TurtleRegistry` 维护所有海龟的 `name / x / y / caught / has_pose`，提供 `nearest_to` 查最近目标。 |

#### 运行配置与打包

| 文件 | 作用 |
| --- | --- |
| `launch/catch_turtle.launch.py` | 一条命令同时起 `turtlesim_node` + 4 个自定义节点，并注入 `params.yaml`。 |
| `config/params.yaml` | 集中所有可调参数（周期、速度、距离阈值、超时、冷却时长），改参数无需重新编译。 |
| `setup.py` | `ament_python` 构建脚本：注册 4 个节点的 console_scripts，把 launch/config 装到 share。 |
| `package.xml` | 声明依赖（`rclpy / std_msgs / geometry_msgs / turtlesim / catch_turtle_interfaces` 等）。 |
| `resource/catch_turtle_bringup` | `ament_index` 占位文件，**保持空，不要删**。 |

## 通信关系

- **Topic**
  - `/turtleN/pose`：`turtlesim` → `master_manager` / `catch_executor` / `follower_manager`
  - `/turtle1/cmd_vel`：`catch_executor` → `turtlesim`
  - `/turtleN/cmd_vel`（N≥2）：`follower_manager` → `turtlesim`
  - `/caught_chain`（JSON）：`master_manager` → `follower_manager`
- **Service**：`/spawn`（`spawn_manager` → `turtlesim`）
- **Action**：`/catch_target`（Client：`master_manager`；Server：`catch_executor`）

## 运行行为

- **新海龟静止**：被 spawn 出来后没人发 `cmd_vel` 给它，会一直停在原地等被抓。
- **动态决策（带抢占）**：`master_manager` 每 0.5 秒重新选一次最近未抓海龟。即使正在抓 `turtleA`，如果新刷的 `turtleB` 距离主海龟 + `preempt_margin`（默认 1.0 m）仍然小于 `turtleA` 的距离，就会 cancel 当前 goal，下一拍切去抓 `turtleB`。带滞回，避免两个目标距离接近时来回切换。被抢占的目标**不进失败冷却**。
- **主海龟动作集**：默认 `{前进, 左转, 右转}`，目标在身后时也走"先转身再前进"。把 `allow_reverse: true` 打开后扩成 `{前进, 后退, 左转, 右转}`：每 tick 比较"面向目标"与"背向目标"两个朝向误差取小的方向走，目标在身后时直接倒车，比 180° 调头快。
- **跟随链**：抓到后加入 `caught_chain`，第一只跟主海龟，后面每一只跟队尾前一只，仅前进 + 转向，不后退。

## 快速开始

```bash
# 把 ros2_ws 同步到 Ubuntu 22.04 + ROS2 Humble 环境
cd ~/ros2_ws
source /opt/ros/humble/setup.bash
colcon build
source install/setup.bash
ros2 launch catch_turtle_bringup catch_turtle.launch.py
```

预期：`turtlesim` 窗口打开 → 每 3 秒新增一只海龟 → `turtle1` 自动追最近目标 → 抓到的海龟依次加入跟随链。
