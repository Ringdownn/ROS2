# Catch Turtle All 编码计划（可直接落地版）

本文档基于 `catch_turtle_implementation_plan.md`（整体方案）和 `ubuntu_ros2_catch_turtle_guide.md` 第 11 点（每个节点的职责），把整个项目拆成**可按顺序落地的编码任务**。

每一节都按下面的格式写：

- **目标**：完成本节后系统多了什么能力
- **要写/改的文件**：本节涉及的文件
- **完整源码**：可直接复制粘贴到对应文件
- **验证步骤**：编完后必须通过的最小验证

> 开发原则：**先骨架、再单功能、再联调**。每完成一节就编译并验证一次。
>
> 默认环境：`Ubuntu 22.04` + `ROS2 Humble` + `Python 3.10` + `rclpy`。

## 0. 编码前的总体约定

### 0.1 包和命名

- 工作区：`~/ros2_ws`
- 接口包：`catch_turtle_interfaces`（`ament_cmake`）
- 主功能包：`catch_turtle_bringup`（`ament_python`）
- 主海龟名：`turtle1`
- 新生成海龟名：`turtle2`、`turtle3`、`turtle4`、…
- 自定义 action：`catch_turtle_interfaces/action/CatchTarget.action`
- 链条同步 topic：`/caught_chain`，类型 `std_msgs/msg/String`，内容是 JSON

### 0.2 节点列表

| 节点 | 类型 | 关键身份 |
| --- | --- | --- |
| `turtlesim_node` | 仿真 | 系统自带，不写代码 |
| `spawn_manager` | Python 节点 | `/spawn` 服务 Client |
| `master_manager` | Python 节点 | Action Client + `/caught_chain` Publisher |
| `catch_executor` | Python 节点 | Action Server + `cmd_vel` Publisher |
| `follower_manager` | Python 节点 | 多 `cmd_vel` Publisher |

### 0.3 并发模型（硬性约束）

- `catch_executor` 必须用 `MultiThreadedExecutor` + `ReentrantCallbackGroup`，否则 Action 执行循环会阻塞订阅。
- `master_manager` 同样必须用 `MultiThreadedExecutor`，否则 Action 回调和定时器决策可能互相阻塞。
- 其它节点单线程即可。

### 0.4 稳定性硬性约束（避免长期跑坏）

- `catch_executor` 必须执行**单 goal 串行化**：忙时收到新 goal 直接 `REJECT`，避免两套控制律同时往 `turtle1/cmd_vel` 发指令。**抢占由 `master_manager` 主动 cancel 旧 goal 实现**，而不是塞两个 goal 进去。
- `master_manager` 抢占必须带**滞回**（`preempt_margin`，默认 1.0 m）：新最近目标距离 + margin < 当前目标距离 才换，避免两个目标距离接近时来回切换。
- `spawn_manager` 必须能优雅处理 `/spawn` 重名失败：失败后**自动跳号继续**，不能卡在同一个名字上反复重试。
- `master_manager` 必须给"抓取失败的目标"加**短期冷却**；**抢占触发的取消不算失败**，不进冷却。
- `catch_executor` 控制律默认仅"前向 + 转向"，把 `allow_reverse` 打开后才比较 forward_err / backward_err 双方向取小走；这是工程开关，**默认关**以贴合"先转再走"的可读演示效果，调试时可改 `params.yaml` 的 `allow_reverse: true` 验证倒车。
- 所有定时器、Action 回调一律放进同一个 `ReentrantCallbackGroup`，避免 `AttributeError` 或单线程死锁。

## 1. 阶段 0：搭建工作区和包骨架

### 1.1 命令

```bash
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src

ros2 pkg create catch_turtle_interfaces --build-type ament_cmake \
  --dependencies action_msgs

ros2 pkg create catch_turtle_bringup --build-type ament_python \
  --dependencies rclpy std_msgs geometry_msgs turtlesim catch_turtle_interfaces
```

### 1.2 最终目录

```text
src/
├── catch_turtle_interfaces/
│   ├── action/
│   │   └── CatchTarget.action
│   ├── CMakeLists.txt
│   └── package.xml
└── catch_turtle_bringup/
    ├── catch_turtle_bringup/
    │   ├── __init__.py
    │   ├── utils.py
    │   ├── turtle_registry.py
    │   ├── spawn_manager.py
    │   ├── master_manager.py
    │   ├── catch_executor.py
    │   └── follower_manager.py
    ├── launch/
    │   └── catch_turtle.launch.py
    ├── config/
    │   └── params.yaml
    ├── resource/
    │   └── catch_turtle_bringup
    ├── setup.py
    └── package.xml
```

### 1.3 验证

```bash
cd ~/ros2_ws
colcon build
source install/setup.bash
ros2 pkg list | grep catch_turtle
```

## 2. 阶段 1：定义自定义 Action 接口

### 2.1 `src/catch_turtle_interfaces/action/CatchTarget.action`

```text
string target_name
---
bool success
string caught_name
---
float32 distance_remaining
```

### 2.2 `src/catch_turtle_interfaces/CMakeLists.txt`（完整内容）

```cmake
cmake_minimum_required(VERSION 3.8)
project(catch_turtle_interfaces)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(action_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "action/CatchTarget.action"
  DEPENDENCIES action_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
```

### 2.3 `src/catch_turtle_interfaces/package.xml`（完整内容）

```xml
<?xml version="1.0"?>
<package format="3">
  <name>catch_turtle_interfaces</name>
  <version>0.1.0</version>
  <description>Action interfaces for the Catch Turtle All project</description>
  <maintainer email="you@example.com">you</maintainer>
  <license>Apache-2.0</license>

  <buildtool_depend>ament_cmake</buildtool_depend>
  <buildtool_depend>rosidl_default_generators</buildtool_depend>

  <depend>action_msgs</depend>

  <exec_depend>rosidl_default_runtime</exec_depend>

  <member_of_group>rosidl_interface_packages</member_of_group>

  <export>
    <build_type>ament_cmake</build_type>
  </export>
</package>
```

### 2.4 验证

```bash
cd ~/ros2_ws
colcon build --packages-select catch_turtle_interfaces
source install/setup.bash
ros2 interface show catch_turtle_interfaces/action/CatchTarget
```

## 3. 阶段 2：工具模块

### 3.1 `src/catch_turtle_bringup/catch_turtle_bringup/__init__.py`

```python
```

（保持空文件即可。）

### 3.2 `src/catch_turtle_bringup/catch_turtle_bringup/utils.py`

```python
"""Math helpers shared by all catch_turtle_bringup nodes."""

from __future__ import annotations

import math


def normalize_angle(theta: float) -> float:
    """Wrap an angle to the [-pi, pi] range."""
    while theta > math.pi:
        theta -= 2.0 * math.pi
    while theta < -math.pi:
        theta += 2.0 * math.pi
    return theta


def distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def angle_to(x_from: float, y_from: float, x_to: float, y_to: float) -> float:
    return math.atan2(y_to - y_from, x_to - x_from)


def clamp(value: float, lo: float, hi: float) -> float:
    if lo > hi:
        lo, hi = hi, lo
    return max(lo, min(hi, value))


def sign(value: float) -> float:
    """Return +1.0 / -1.0 / 0.0 mirroring math.copysign but keeping zero as zero."""
    if value > 0.0:
        return 1.0
    if value < 0.0:
        return -1.0
    return 0.0
```

### 3.3 `src/catch_turtle_bringup/catch_turtle_bringup/turtle_registry.py`

> 设计原则：只保留**当前真正用到**的字段和方法，避免"以备后用"的死代码。
> `TurtleEntry` 只存 `name / x / y / caught / has_pose` 五个字段；`TurtleRegistry` 只暴露 5 个方法（`add / update_pose / mark_caught / get / nearest_to`）。

```python
"""Internal registry for tracking all turtles known to the system."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from . import utils


@dataclass
class TurtleEntry:
    name: str
    x: float = 0.0
    y: float = 0.0
    caught: bool = False
    has_pose: bool = False


class TurtleRegistry:
    """Holds the live state of every turtle the system has seen."""

    def __init__(self) -> None:
        self._turtles: Dict[str, TurtleEntry] = {}

    def add(self, name: str) -> TurtleEntry:
        if name not in self._turtles:
            self._turtles[name] = TurtleEntry(name=name)
        return self._turtles[name]

    def update_pose(self, name: str, x: float, y: float) -> None:
        entry = self._turtles.get(name)
        if entry is None:
            entry = self.add(name)
        entry.x = x
        entry.y = y
        entry.has_pose = True

    def mark_caught(self, name: str) -> None:
        entry = self._turtles.get(name)
        if entry is not None:
            entry.caught = True

    def get(self, name: str) -> Optional[TurtleEntry]:
        return self._turtles.get(name)

    def uncaught_targets(self, exclude: Optional[List[str]] = None) -> List[TurtleEntry]:
        excluded = set(exclude or [])
        return [
            t for t in self._turtles.values()
            if t.has_pose and not t.caught and t.name not in excluded
        ]

    def nearest_to(self, x: float, y: float,
                   exclude: Optional[List[str]] = None) -> Optional[TurtleEntry]:
        candidates = self.uncaught_targets(exclude=exclude)
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda t: utils.distance(x, y, t.x, t.y),
        )
```

## 4. 阶段 3：`spawn_manager`

### 4.1 `src/catch_turtle_bringup/catch_turtle_bringup/spawn_manager.py`

```python
"""Periodically spawn new turtles in turtlesim.

Robustness features:
- On startup, scans existing /turtleN/pose topics and starts numbering from
  max(existing) + 1, so a restart of this node never collides with surviving
  turtles.
- If turtlesim refuses to spawn (returns an empty name), automatically bumps
  the index and retries on the next tick instead of getting stuck forever.
"""

from __future__ import annotations

import math
import random
import re

import rclpy
from rclpy.node import Node
from turtlesim.srv import Spawn


_TURTLE_NAME_RE = re.compile(r'^/turtle(\d+)/pose$')


class SpawnManagerNode(Node):
    def __init__(self) -> None:
        super().__init__('spawn_manager')

        self.declare_parameter('spawn_period', 3.0)
        self.declare_parameter('x_min', 1.0)
        self.declare_parameter('x_max', 10.0)
        self.declare_parameter('y_min', 1.0)
        self.declare_parameter('y_max', 10.0)
        self.declare_parameter('start_index', 2)
        self.declare_parameter('max_consecutive_failures', 5)

        configured_start = int(self.get_parameter('start_index').value)
        self._next_index: int = max(configured_start, self._scan_existing_index() + 1)
        self._pending: bool = False
        self._consecutive_failures: int = 0

        self._client = self.create_client(Spawn, '/spawn')
        while not self._client.wait_for_service(timeout_sec=2.0):
            self.get_logger().warn('Waiting for /spawn service to become available...')

        period = float(self.get_parameter('spawn_period').value)
        self._timer = self.create_timer(period, self._on_timer)
        self.get_logger().info(
            f'spawn_manager up; period={period:.2f}s; first_name=turtle{self._next_index}'
        )

    def _scan_existing_index(self) -> int:
        max_idx = 1
        for topic_name, _types in self.get_topic_names_and_types():
            match = _TURTLE_NAME_RE.match(topic_name)
            if match:
                max_idx = max(max_idx, int(match.group(1)))
        return max_idx

    def _on_timer(self) -> None:
        if self._pending:
            return

        x_min = float(self.get_parameter('x_min').value)
        x_max = float(self.get_parameter('x_max').value)
        y_min = float(self.get_parameter('y_min').value)
        y_max = float(self.get_parameter('y_max').value)

        x = random.uniform(x_min, x_max)
        y = random.uniform(y_min, y_max)
        theta = random.uniform(-math.pi, math.pi)
        name = f'turtle{self._next_index}'

        request = Spawn.Request()
        request.x = float(x)
        request.y = float(y)
        request.theta = float(theta)
        request.name = name

        self._pending = True
        future = self._client.call_async(request)
        future.add_done_callback(lambda f, n=name: self._on_response(f, n))

    def _on_response(self, future, requested_name: str) -> None:
        self._pending = False
        try:
            result = future.result()
        except Exception as exc:
            self.get_logger().error(f'Spawn call failed for {requested_name}: {exc}')
            self._handle_failure()
            return
        if result is None:
            self.get_logger().warn(f'Spawn returned no result for {requested_name}.')
            self._handle_failure()
            return

        if not result.name:
            # turtlesim signals duplicate-name / invalid-pose by returning an empty name
            self.get_logger().warn(
                f'Spawn rejected {requested_name} (likely duplicate); skipping index'
            )
            self._next_index += 1
            self._handle_failure()
            return

        self.get_logger().info(f'Spawned new turtle: {result.name}')
        self._next_index += 1
        self._consecutive_failures = 0

    def _handle_failure(self) -> None:
        self._consecutive_failures += 1
        limit = int(self.get_parameter('max_consecutive_failures').value)
        if self._consecutive_failures >= limit:
            # Re-scan in case a teammate manually spawned turtles meanwhile.
            scanned = self._scan_existing_index() + 1
            if scanned > self._next_index:
                self.get_logger().warn(
                    f'Resyncing next_index {self._next_index} -> {scanned}'
                )
                self._next_index = scanned
            self._consecutive_failures = 0


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SpawnManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
```

### 4.2 验证（先把 `setup.py` 的 entry point 加上，见第 11 节，再编译）

```bash
ros2 run turtlesim turtlesim_node                  # 终端 1
ros2 run catch_turtle_bringup spawn_manager        # 终端 2
ros2 topic list | grep pose                        # 终端 3
```

预期：每 3 秒地图上多一只海龟，`/turtle2/pose`、`/turtle3/pose`… 持续增加。

## 5. 阶段 4：`catch_executor`（Action Server：单 goal 串行 + 超时 + 多线程执行器）

### 5.1 `src/catch_turtle_bringup/catch_turtle_bringup/catch_executor.py`

```python
"""Action server that drives turtle1 to catch a target turtle.

Stability features:
- Single-goal serialization: while one goal is executing, any new goal is
  REJECTED so two control loops never fight for /turtle1/cmd_vel.
- Hard timeouts: every goal has a total timeout and a "no pose received"
  timeout, after which it is aborted with success=False.
- MultiThreadedExecutor + ReentrantCallbackGroup, so the long-running
  execute callback never blocks pose subscriptions.

Motion:
- Action set = {forward, backward, turn-left, turn-right}. Each control tick
  evaluates whether facing the target (forward) or the opposite direction
  (backward) yields the smaller heading error, and drives in that direction.
  When `allow_reverse` is False the controller falls back to forward-only.
"""

from __future__ import annotations

import math
import threading
import time
from typing import Optional

import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from geometry_msgs.msg import Twist
from turtlesim.msg import Pose

from catch_turtle_interfaces.action import CatchTarget

from . import utils


class CatchExecutorNode(Node):
    def __init__(self) -> None:
        super().__init__('catch_executor')

        self.declare_parameter('master_name', 'turtle1')
        self.declare_parameter('linear_speed', 1.5)
        self.declare_parameter('angular_speed', 3.0)
        self.declare_parameter('max_angular_speed', 4.0)
        self.declare_parameter('catch_distance', 0.5)
        self.declare_parameter('angle_tolerance', 0.1)
        self.declare_parameter('control_rate_hz', 20.0)
        self.declare_parameter('goal_timeout_sec', 30.0)
        self.declare_parameter('no_pose_timeout_sec', 5.0)
        self.declare_parameter('allow_reverse', False)

        self._master_name: str = str(self.get_parameter('master_name').value)
        self._cb_group = ReentrantCallbackGroup()

        self._master_pose: Optional[Pose] = None
        self._target_pose: Optional[Pose] = None
        self._target_lock = threading.Lock()

        self._busy_lock = threading.Lock()
        self._busy: bool = False

        self._cmd_pub = self.create_publisher(
            Twist, f'/{self._master_name}/cmd_vel', 10,
        )
        self.create_subscription(
            Pose, f'/{self._master_name}/pose',
            self._on_master_pose, 10,
            callback_group=self._cb_group,
        )

        self._action_server = ActionServer(
            self,
            CatchTarget,
            'catch_target',
            execute_callback=self._execute,
            goal_callback=self._on_goal,
            cancel_callback=self._on_cancel,
            callback_group=self._cb_group,
        )

        self.get_logger().info('catch_executor ready, action: /catch_target')

    def _on_master_pose(self, msg: Pose) -> None:
        self._master_pose = msg

    def _on_target_pose(self, msg: Pose) -> None:
        with self._target_lock:
            self._target_pose = msg

    def _try_acquire_busy(self) -> bool:
        with self._busy_lock:
            if self._busy:
                return False
            self._busy = True
            return True

    def _release_busy(self) -> None:
        with self._busy_lock:
            self._busy = False

    def _on_goal(self, _goal_request) -> GoalResponse:
        # Serialize: only one catch goal may run at a time.
        if self._busy:
            self.get_logger().warn('Rejecting new goal: another catch is in progress')
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    @staticmethod
    def _on_cancel(_goal_handle) -> CancelResponse:
        return CancelResponse.ACCEPT

    def _publish_zero(self) -> None:
        self._cmd_pub.publish(Twist())

    def _execute(self, goal_handle) -> CatchTarget.Result:
        target_name: str = goal_handle.request.target_name
        self.get_logger().info(f'Catch goal received: {target_name}')

        # _on_goal already enforced single-goal, but mark busy explicitly so
        # _release_busy is paired with the entire execute lifetime.
        if not self._try_acquire_busy():
            self.get_logger().warn(
                f'Race detected, aborting goal {target_name}'
            )
            goal_handle.abort()
            result = CatchTarget.Result()
            result.success = False
            result.caught_name = ''
            return result

        with self._target_lock:
            self._target_pose = None
        target_sub = self.create_subscription(
            Pose, f'/{target_name}/pose',
            self._on_target_pose, 10,
            callback_group=self._cb_group,
        )

        rate_hz = float(self.get_parameter('control_rate_hz').value)
        period = 1.0 / max(rate_hz, 1.0)
        catch_distance = float(self.get_parameter('catch_distance').value)
        angle_tolerance = float(self.get_parameter('angle_tolerance').value)
        linear_speed = float(self.get_parameter('linear_speed').value)
        angular_speed = float(self.get_parameter('angular_speed').value)
        max_angular_speed = float(self.get_parameter('max_angular_speed').value)
        goal_timeout_sec = float(self.get_parameter('goal_timeout_sec').value)
        no_pose_timeout_sec = float(self.get_parameter('no_pose_timeout_sec').value)
        allow_reverse = bool(self.get_parameter('allow_reverse').value)

        result = CatchTarget.Result()
        result.success = False
        result.caught_name = ''

        start_time = time.monotonic()
        first_pose_time: Optional[float] = None

        try:
            while rclpy.ok():
                if goal_handle.is_cancel_requested:
                    self._publish_zero()
                    goal_handle.canceled()
                    self.get_logger().info(f'Goal canceled for {target_name}')
                    return result

                now = time.monotonic()
                if now - start_time > goal_timeout_sec:
                    self._publish_zero()
                    goal_handle.abort()
                    self.get_logger().warn(
                        f'Goal {target_name} aborted: total timeout',
                    )
                    return result

                with self._target_lock:
                    target_pose = self._target_pose
                master_pose = self._master_pose

                if target_pose is None or master_pose is None:
                    if first_pose_time is None and now - start_time > no_pose_timeout_sec:
                        self._publish_zero()
                        goal_handle.abort()
                        self.get_logger().warn(
                            f'Goal {target_name} aborted: no pose received',
                        )
                        return result
                    self._publish_zero()
                    time.sleep(period)
                    continue

                if first_pose_time is None:
                    first_pose_time = now

                dx = target_pose.x - master_pose.x
                dy = target_pose.y - master_pose.y
                dist = (dx * dx + dy * dy) ** 0.5

                feedback = CatchTarget.Feedback()
                feedback.distance_remaining = float(dist)
                goal_handle.publish_feedback(feedback)

                if dist < catch_distance:
                    self._publish_zero()
                    result.success = True
                    result.caught_name = target_name
                    goal_handle.succeed()
                    self.get_logger().info(f'Caught {target_name}!')
                    return result

                target_angle = utils.angle_to(
                    master_pose.x, master_pose.y, target_pose.x, target_pose.y,
                )
                forward_err = utils.normalize_angle(
                    target_angle - master_pose.theta
                )
                if allow_reverse:
                    backward_err = utils.normalize_angle(
                        forward_err - math.pi
                    )
                    if abs(backward_err) < abs(forward_err):
                        direction = -1.0
                        heading_err = backward_err
                    else:
                        direction = 1.0
                        heading_err = forward_err
                else:
                    direction = 1.0
                    heading_err = forward_err

                twist = Twist()
                if abs(heading_err) > angle_tolerance:
                    twist.angular.z = utils.clamp(
                        angular_speed * utils.sign(heading_err),
                        -max_angular_speed, max_angular_speed,
                    )
                else:
                    twist.linear.x = direction * linear_speed
                    twist.angular.z = utils.clamp(
                        2.0 * heading_err,
                        -max_angular_speed, max_angular_speed,
                    )
                self._cmd_pub.publish(twist)

                time.sleep(period)
        finally:
            self.destroy_subscription(target_sub)
            self._publish_zero()
            self._release_busy()

        return result


def main(args=None) -> None:
    rclpy.init(args=args)
    node = CatchExecutorNode()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
```

### 5.2 验证

```bash
ros2 run turtlesim turtlesim_node                       # 终端 1
ros2 run catch_turtle_bringup spawn_manager             # 终端 2
ros2 run catch_turtle_bringup catch_executor            # 终端 3
# 等地图上出现 turtle2 后
ros2 action send_goal /catch_target \
  catch_turtle_interfaces/action/CatchTarget \
  "{target_name: 'turtle2'}" --feedback                 # 终端 4
```

预期：feedback 中的 `distance_remaining` 持续减小，最终返回 `success: true, caught_name: turtle2`。

## 6. 阶段 5：`master_manager`

### 6.1 `src/catch_turtle_bringup/catch_turtle_bringup/master_manager.py`

```python
"""Brain of the system: discover turtles, pick the nearest, dispatch catch goals.

Stability features:
- Per-target failure cooldown: if catch_executor reports failure / abort /
  rejection for a turtle, that turtle is excluded from the candidate set for
  `failure_cooldown_sec` seconds, so we don't lock onto a broken target.
- Auto-discovery: scans `/turtleN/pose` topics each tick, so newly spawned
  turtles are picked up without any explicit hand-off.

Dynamic decision:
- Even while a catch goal is in flight, every `decision_period` we re-pick the
  nearest uncaught turtle. If it is closer than the current target by more
  than `preempt_margin` meters, we cancel the current goal (preemption) and
  let the next decision tick dispatch the closer one. The hysteresis prevents
  flip-flopping between two near-equidistant targets.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional

import rclpy
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from std_msgs.msg import String
from turtlesim.msg import Pose

from catch_turtle_interfaces.action import CatchTarget

from . import utils
from .turtle_registry import TurtleRegistry


_POSE_TOPIC_RE = re.compile(r'^/(turtle\d+)/pose$')


class MasterManagerNode(Node):
    def __init__(self) -> None:
        super().__init__('master_manager')

        self.declare_parameter('master_name', 'turtle1')
        self.declare_parameter('discover_period', 1.0)
        self.declare_parameter('decision_period', 0.5)
        self.declare_parameter('failure_cooldown_sec', 5.0)
        self.declare_parameter('action_server_wait_sec', 2.0)
        self.declare_parameter('preempt_margin', 1.0)

        self._master_name: str = str(self.get_parameter('master_name').value)
        self._cb_group = ReentrantCallbackGroup()

        self._registry = TurtleRegistry()
        self._registry.add(self._master_name)

        self._chain: List[str] = []
        self._goal_in_flight: bool = False
        self._current_target: Optional[str] = None
        self._goal_handle: Any = None
        self._preempting: bool = False
        self._failed_until: Dict[str, float] = {}

        self._pose_subs: Dict[str, Any] = {}
        self._subscribe_pose(self._master_name)

        self._chain_pub = self.create_publisher(String, '/caught_chain', 10)

        self._action_client = ActionClient(
            self, CatchTarget, 'catch_target',
            callback_group=self._cb_group,
        )

        self.create_timer(
            float(self.get_parameter('discover_period').value),
            self._discover_topics,
            callback_group=self._cb_group,
        )
        self.create_timer(
            float(self.get_parameter('decision_period').value),
            self._decide_and_dispatch,
            callback_group=self._cb_group,
        )

        self.get_logger().info('master_manager up')

    def _subscribe_pose(self, name: str) -> None:
        if name in self._pose_subs:
            return
        sub = self.create_subscription(
            Pose, f'/{name}/pose',
            lambda msg, n=name: self._on_pose(n, msg),
            10,
            callback_group=self._cb_group,
        )
        self._pose_subs[name] = sub
        self._registry.add(name)
        self.get_logger().info(f'Tracking pose of {name}')

    def _discover_topics(self) -> None:
        for topic_name, _types in self.get_topic_names_and_types():
            match = _POSE_TOPIC_RE.match(topic_name)
            if not match:
                continue
            turtle_name = match.group(1)
            if turtle_name not in self._pose_subs:
                self._subscribe_pose(turtle_name)

    def _on_pose(self, name: str, msg: Pose) -> None:
        self._registry.update_pose(name, msg.x, msg.y)

    def _cooldown_excluded(self) -> List[str]:
        now = time.monotonic()
        for name in list(self._failed_until.keys()):
            if self._failed_until[name] <= now:
                del self._failed_until[name]
        return list(self._failed_until.keys())

    def _mark_failed(self, target_name: Optional[str]) -> None:
        if not target_name:
            return
        cooldown = float(self.get_parameter('failure_cooldown_sec').value)
        self._failed_until[target_name] = time.monotonic() + max(cooldown, 0.0)
        self.get_logger().warn(
            f'Target {target_name} on cooldown for {cooldown:.1f}s'
        )

    def _decide_and_dispatch(self) -> None:
        master = self._registry.get(self._master_name)
        if master is None or not master.has_pose:
            return

        excluded = [self._master_name] + self._chain + self._cooldown_excluded()
        target = self._registry.nearest_to(master.x, master.y, exclude=excluded)
        if target is None:
            return

        if self._goal_in_flight:
            self._maybe_preempt(master, target)
            return

        self._current_target = target.name
        self._goal_in_flight = True
        self._send_goal(target.name)

    def _maybe_preempt(self, master, candidate) -> None:
        if self._preempting:
            return
        if self._current_target is None or candidate.name == self._current_target:
            return
        if self._goal_handle is None:
            return

        current_entry = self._registry.get(self._current_target)
        if current_entry is None or not current_entry.has_pose:
            return

        cur_dist = utils.distance(
            master.x, master.y, current_entry.x, current_entry.y,
        )
        new_dist = utils.distance(
            master.x, master.y, candidate.x, candidate.y,
        )
        margin = float(self.get_parameter('preempt_margin').value)
        if new_dist + margin >= cur_dist:
            return

        self.get_logger().info(
            f'Preempting {self._current_target} ({cur_dist:.2f}m) '
            f'-> {candidate.name} ({new_dist:.2f}m)'
        )
        self._preempting = True
        cancel_future = self._goal_handle.cancel_goal_async()
        cancel_future.add_done_callback(self._on_cancel_done)

    def _on_cancel_done(self, _future) -> None:
        # The result callback will fire shortly after; bookkeeping is done there.
        pass

    def _send_goal(self, target_name: str) -> None:
        wait_sec = float(self.get_parameter('action_server_wait_sec').value)
        if not self._action_client.wait_for_server(timeout_sec=wait_sec):
            self.get_logger().warn('catch_target action server not available')
            self._reset_goal_state()
            return

        goal = CatchTarget.Goal()
        goal.target_name = target_name
        self.get_logger().info(f'Dispatching catch goal: {target_name}')
        send_future = self._action_client.send_goal_async(goal)
        send_future.add_done_callback(self._on_goal_response)

    def _on_goal_response(self, future) -> None:
        try:
            handle = future.result()
        except Exception as exc:
            self.get_logger().error(f'send_goal failed: {exc}')
            self._mark_failed(self._current_target)
            self._reset_goal_state()
            return

        if not handle.accepted:
            self.get_logger().warn(
                f'Catch goal for {self._current_target} was rejected'
            )
            self._mark_failed(self._current_target)
            self._reset_goal_state()
            return

        self._goal_handle = handle
        handle.get_result_async().add_done_callback(self._on_result)

    def _on_result(self, future) -> None:
        was_preempting = self._preempting
        try:
            wrapper = future.result()
        except Exception as exc:
            self.get_logger().error(f'get_result failed: {exc}')
            if not was_preempting:
                self._mark_failed(self._current_target)
            self._reset_goal_state()
            return

        result = wrapper.result
        if result is not None and result.success and result.caught_name:
            self._registry.mark_caught(result.caught_name)
            if result.caught_name not in self._chain:
                self._chain.append(result.caught_name)
            self._failed_until.pop(result.caught_name, None)
            self._publish_chain()
            self.get_logger().info(
                f'Chain updated -> {self._chain}',
            )
        elif was_preempting:
            self.get_logger().info(
                f'Preempted goal for {self._current_target}; '
                'next decision tick will pick the closer target'
            )
        else:
            self.get_logger().warn(
                f'Catch goal for {self._current_target} did not succeed'
            )
            self._mark_failed(self._current_target)

        self._reset_goal_state()

    def _reset_goal_state(self) -> None:
        self._goal_in_flight = False
        self._current_target = None
        self._goal_handle = None
        self._preempting = False

    def _publish_chain(self) -> None:
        msg = String()
        msg.data = json.dumps({
            'leader': self._master_name,
            'chain': self._chain,
        })
        self._chain_pub.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = MasterManagerNode()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
```

### 6.2 验证

```bash
ros2 run turtlesim turtlesim_node                  # 终端 1
ros2 run catch_turtle_bringup spawn_manager        # 终端 2
ros2 run catch_turtle_bringup catch_executor       # 终端 3
ros2 run catch_turtle_bringup master_manager       # 终端 4
ros2 topic echo /caught_chain                      # 终端 5
```

预期：`turtle1` 自动一只接一只地抓海龟，`/caught_chain` 每抓到一只就更新一次。

## 7. 阶段 6：`follower_manager`

### 7.1 `src/catch_turtle_bringup/catch_turtle_bringup/follower_manager.py`

```python
"""Make every caught turtle follow its predecessor in the chain."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Twist
from std_msgs.msg import String
from turtlesim.msg import Pose

from . import utils


class FollowerManagerNode(Node):
    def __init__(self) -> None:
        super().__init__('follower_manager')

        self.declare_parameter('leader_name', 'turtle1')
        self.declare_parameter('follow_distance', 0.8)
        self.declare_parameter('linear_speed', 1.2)
        self.declare_parameter('angular_speed', 2.5)
        self.declare_parameter('max_angular_speed', 3.5)
        self.declare_parameter('angle_tolerance', 0.15)
        self.declare_parameter('control_rate_hz', 20.0)
        self.declare_parameter('linear_kp', 1.0)
        self.declare_parameter('angular_kp', 4.0)

        self._leader_name: str = str(self.get_parameter('leader_name').value)
        self._chain: List[str] = []
        self._poses: Dict[str, Pose] = {}
        self._cmd_pubs: Dict[str, Any] = {}
        self._pose_subs: Dict[str, Any] = {}

        self._ensure_pose_sub(self._leader_name)

        self.create_subscription(
            String, '/caught_chain', self._on_chain, 10,
        )

        period = 1.0 / float(self.get_parameter('control_rate_hz').value)
        self.create_timer(period, self._on_tick)

        self.get_logger().info('follower_manager up')

    def _ensure_pose_sub(self, name: str) -> None:
        if name in self._pose_subs:
            return
        sub = self.create_subscription(
            Pose, f'/{name}/pose',
            lambda msg, n=name: self._on_pose(n, msg),
            10,
        )
        self._pose_subs[name] = sub

    def _ensure_cmd_pub(self, name: str) -> None:
        if name in self._cmd_pubs:
            return
        self._cmd_pubs[name] = self.create_publisher(
            Twist, f'/{name}/cmd_vel', 10,
        )

    def _on_pose(self, name: str, msg: Pose) -> None:
        self._poses[name] = msg

    def _on_chain(self, msg: String) -> None:
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warn('Bad /caught_chain payload')
            return

        leader = data.get('leader', self._leader_name)
        chain = data.get('chain', [])
        if not isinstance(chain, list):
            return

        self._leader_name = leader
        self._chain = [str(n) for n in chain]

        self._ensure_pose_sub(self._leader_name)
        for name in self._chain:
            self._ensure_pose_sub(name)
            self._ensure_cmd_pub(name)

    def _on_tick(self) -> None:
        if not self._chain:
            return

        follow_distance = float(self.get_parameter('follow_distance').value)
        linear_speed = float(self.get_parameter('linear_speed').value)
        angular_speed = float(self.get_parameter('angular_speed').value)
        max_angular_speed = float(self.get_parameter('max_angular_speed').value)
        angle_tolerance = float(self.get_parameter('angle_tolerance').value)
        linear_kp = float(self.get_parameter('linear_kp').value)
        angular_kp = float(self.get_parameter('angular_kp').value)

        for i, follower in enumerate(self._chain):
            leader = self._leader_name if i == 0 else self._chain[i - 1]

            f_pose: Optional[Pose] = self._poses.get(follower)
            l_pose: Optional[Pose] = self._poses.get(leader)
            pub = self._cmd_pubs.get(follower)
            if f_pose is None or l_pose is None or pub is None:
                continue

            dist = utils.distance(f_pose.x, f_pose.y, l_pose.x, l_pose.y)
            twist = Twist()

            if dist < follow_distance:
                pub.publish(twist)
                continue

            target_angle = utils.angle_to(
                f_pose.x, f_pose.y, l_pose.x, l_pose.y,
            )
            angle_err = utils.normalize_angle(target_angle - f_pose.theta)

            if abs(angle_err) > angle_tolerance:
                twist.angular.z = utils.clamp(
                    angular_speed * utils.sign(angle_err),
                    -max_angular_speed, max_angular_speed,
                )
            else:
                twist.linear.x = utils.clamp(
                    linear_kp * (dist - follow_distance),
                    0.0, linear_speed,
                )
                twist.angular.z = utils.clamp(
                    angular_kp * angle_err,
                    -max_angular_speed, max_angular_speed,
                )
            pub.publish(twist)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = FollowerManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
```

### 7.2 验证

接着上一阶段，再开一个终端：

```bash
ros2 run catch_turtle_bringup follower_manager
```

预期：每抓到一只海龟，它就尾随队尾，逐渐形成龟队。

## 8. 阶段 7：`params.yaml`

### 8.1 `src/catch_turtle_bringup/config/params.yaml`

```yaml
spawn_manager:
  ros__parameters:
    spawn_period: 3.0
    x_min: 1.0
    x_max: 10.0
    y_min: 1.0
    y_max: 10.0
    start_index: 2
    max_consecutive_failures: 5

master_manager:
  ros__parameters:
    master_name: 'turtle1'
    discover_period: 1.0
    decision_period: 0.5
    failure_cooldown_sec: 5.0
    action_server_wait_sec: 2.0
    preempt_margin: 1.0

catch_executor:
  ros__parameters:
    master_name: 'turtle1'
    linear_speed: 1.5
    angular_speed: 3.0
    max_angular_speed: 4.0
    catch_distance: 0.5
    angle_tolerance: 0.1
    control_rate_hz: 20.0
    goal_timeout_sec: 30.0
    no_pose_timeout_sec: 5.0
    allow_reverse: false

follower_manager:
  ros__parameters:
    leader_name: 'turtle1'
    follow_distance: 0.8
    linear_speed: 1.2
    angular_speed: 2.5
    max_angular_speed: 3.5
    angle_tolerance: 0.15
    control_rate_hz: 20.0
    linear_kp: 1.0
    angular_kp: 4.0
```

## 9. 阶段 8：`launch` 文件

### 9.1 `src/catch_turtle_bringup/launch/catch_turtle.launch.py`

```python
"""Launch the entire Catch Turtle All system with one command."""

from __future__ import annotations

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    pkg_share = get_package_share_directory('catch_turtle_bringup')
    params_file = os.path.join(pkg_share, 'config', 'params.yaml')

    return LaunchDescription([
        Node(
            package='turtlesim',
            executable='turtlesim_node',
            name='turtlesim_node',
            output='screen',
        ),
        Node(
            package='catch_turtle_bringup',
            executable='spawn_manager',
            name='spawn_manager',
            parameters=[params_file],
            output='screen',
        ),
        Node(
            package='catch_turtle_bringup',
            executable='catch_executor',
            name='catch_executor',
            parameters=[params_file],
            output='screen',
        ),
        Node(
            package='catch_turtle_bringup',
            executable='master_manager',
            name='master_manager',
            parameters=[params_file],
            output='screen',
        ),
        Node(
            package='catch_turtle_bringup',
            executable='follower_manager',
            name='follower_manager',
            parameters=[params_file],
            output='screen',
        ),
    ])
```

### 9.2 验证

```bash
cd ~/ros2_ws
colcon build
source install/setup.bash
ros2 launch catch_turtle_bringup catch_turtle.launch.py
```

预期：一次性启动 `turtlesim` 与四个自定义节点；海龟生成、被抓、加入跟随链，全程无需手动干预。

## 10. `setup.py` 与 `package.xml`

### 10.1 `src/catch_turtle_bringup/setup.py`

```python
from glob import glob

from setuptools import setup

package_name = 'catch_turtle_bringup'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.py')),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='you',
    maintainer_email='you@example.com',
    description='Catch Turtle All bringup nodes (spawn/master/catch/follower).',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'spawn_manager = catch_turtle_bringup.spawn_manager:main',
            'master_manager = catch_turtle_bringup.master_manager:main',
            'catch_executor = catch_turtle_bringup.catch_executor:main',
            'follower_manager = catch_turtle_bringup.follower_manager:main',
        ],
    },
)
```

### 10.2 `src/catch_turtle_bringup/package.xml`

```xml
<?xml version="1.0"?>
<package format="3">
  <name>catch_turtle_bringup</name>
  <version>0.1.0</version>
  <description>Catch Turtle All bringup nodes.</description>
  <maintainer email="you@example.com">you</maintainer>
  <license>Apache-2.0</license>

  <buildtool_depend>ament_python</buildtool_depend>

  <depend>rclpy</depend>
  <depend>std_msgs</depend>
  <depend>geometry_msgs</depend>
  <depend>turtlesim</depend>
  <depend>catch_turtle_interfaces</depend>

  <exec_depend>launch</exec_depend>
  <exec_depend>launch_ros</exec_depend>

  <test_depend>ament_copyright</test_depend>
  <test_depend>ament_flake8</test_depend>
  <test_depend>ament_pep257</test_depend>
  <test_depend>python3-pytest</test_depend>

  <export>
    <build_type>ament_python</build_type>
  </export>
</package>
```

### 10.3 `src/catch_turtle_bringup/resource/catch_turtle_bringup`

`ros2 pkg create` 已经替你建好这个空文件，不要删，也不要写内容。

## 11. 编码总顺序（按文件粒度）

每写完一项就 `cd ~/ros2_ws && colcon build && source install/setup.bash`，再跑该步骤的"验证"。

1. 创建 `catch_turtle_interfaces` 和 `catch_turtle_bringup` 两个空包（第 1 节）
2. 写 `CatchTarget.action` + `CMakeLists.txt` + `package.xml`（第 2 节）
3. 写 `utils.py`（第 3.2 节）
4. 写 `turtle_registry.py`（第 3.3 节）
5. 把 `setup.py` / `package.xml` 收尾（第 10 节），后面每加一个节点都已注册过 entry_point
6. 写 `spawn_manager.py`（第 4 节），验证
7. 写 `catch_executor.py`（第 5 节），用 `ros2 action send_goal` 单独验证
8. 写 `master_manager.py`（第 6 节），验证整条抓捕循环
9. 写 `follower_manager.py`（第 7 节），验证链条
10. 写 `params.yaml`（第 8 节）
11. 写 `catch_turtle.launch.py`（第 9 节），单命令启动

## 12. 实现期间最容易踩的坑（已在本计划代码里防住的，请勿移除）

- **新海龟生成后没及时订阅它的 `/pose`**：`master_manager._discover_topics` 定时扫 `get_topic_names_and_types`，比"被通知"更稳。
- **重复抓同一只**：抓到就 `mark_caught`；选目标时排除 `chain` 里的所有名字。
- **`spawn_manager` 撞到重名永久卡死**：`/spawn` 失败（返回空 `name`）时自动 `_next_index += 1` 并跳号；启动时先扫一次现有 `turtleN` 取最大值 +1。
- **同时收到两个 catch goal，控制律抢 `cmd_vel`**：`catch_executor._on_goal` 在忙时 `REJECT`，单 goal 串行；`_busy` 与 `_release_busy` 配对在 `try/finally`。
- **抢占抖动**：`master_manager._maybe_preempt` 必须带 `preempt_margin` 滞回，距离差不够就不换；同一时刻只允许一个抢占在路上（`_preempting`）。
- **抢占被误判为失败 → 进了冷却 → 永远抓不到**：`_on_result` 用 `was_preempting` 标志区分"我自己 cancel 的"和"executor 真的失败"，前者不进 `_failed_until`。
- **后退控制律误把目标当背后目标导致原地反复倒车**：`catch_executor` 用 `abs(backward_err) < abs(forward_err)` 严格比较，相等情况下默认走前向，且转向阶段 `linear.x = 0` 不动只转。
- **失败目标被反复抓**：`master_manager._failed_until` 给失败目标加 `failure_cooldown_sec` 的冷却，下一轮自动跳过。
- **Action 执行中又来新目标**：要么走抢占路径（明显更近），要么用 `_goal_in_flight` 屏蔽，不会重复发 goal。
- **角度没归一化**：所有差值都过 `utils.normalize_angle`。
- **跟随链抖动**：`follow_distance` 不要给太小（≥0.8）；离得近主动减速；角度大时只转不动。
- **Action Server 在单线程 executor 里阻塞订阅**：本计划已强制 `MultiThreadedExecutor` + `ReentrantCallbackGroup`，请保留。
- **Action 死循环**：本计划已加入 `goal_timeout_sec` / `no_pose_timeout_sec`，请勿移除。

## 13. 验收标准

- 一句 `ros2 launch catch_turtle_bringup catch_turtle.launch.py` 能起整套系统
- 每 3 秒地图上多一只海龟
- 主海龟自动追最近的未抓海龟，到 0.5 距离内判定抓到
- 抓到的海龟稳定地跟随它的前一只，链条持续增长
- 持续运行 3 分钟以上不崩、不卡死、不重复抓同一只
- `ros2 action list`、`ros2 topic list`、`ros2 node list` 输出符合设计
- 通过 `params.yaml` 调整参数无需改源码
