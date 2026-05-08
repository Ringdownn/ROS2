# Catch Turtle All 整批迁移到虚拟机后的快速验证流程

本文是 `catch_turtle_coding_plan.md` 的姊妹篇。

- `catch_turtle_coding_plan.md` 面向 **"从零开始写代码"** 的场景：每写一个文件就编译一次、验证一次。
- 本文档面向 **"代码已经写好（通过 git 仓库拉取或文件拷贝整批迁移到虚拟机），只需要在 VM 上验证它能跑"** 的场景：**一次编译 + 五次功能验证**。

> 默认环境：`Ubuntu 22.04` + `ROS2 Humble` + `Python 3.10` + `rclpy`。
>
> 工作区：`~/ROS2/ros2_ws`（与 `catch_turtle_coding_plan.md` 0.1 节一致）。

## 0. 通用约定

### 0.1 每个新终端的"开场白"

后面所有"终端 N"的命令前面都默认要先做这两步（之后正文不再重复）：

```bash
cd ~/ROS2/ros2_ws
source install/setup.bash
```

要求 `~/.bashrc` 里已经 `source /opt/ros/humble/setup.bash`；否则手动 source 一次再继续。

### 0.2 本文档预设你已经做过的事

- 已经 `git clone`（或其它方式）把整套源码放进了 `~/ROS2/ros2_ws/src/` 下，包含
  - `catch_turtle_interfaces/`
  - `catch_turtle_bringup/`
- 还**没有**在 VM 上跑过 `colcon build`（如果跑过、且要重测，先 `rm -rf build install log` 清干净）。

## 1. 阶段 A：迁移完整性自检（5 分钟）

这一节只用 **1 个终端**，不启动任何 ROS 节点。

### 1.1 目录结构

```bash
cd ~/ROS2/ros2_ws
sudo apt install -y tree    # 已安装可跳过
tree src -L 3
```

预期输出（顺序无所谓，文件不能少）：

```text
src
├── catch_turtle_bringup
│   ├── catch_turtle_bringup
│   │   ├── __init__.py
│   │   ├── catch_executor.py
│   │   ├── follower_manager.py
│   │   ├── master_manager.py
│   │   ├── spawn_manager.py
│   │   ├── turtle_registry.py
│   │   └── utils.py
│   ├── config
│   │   └── params.yaml
│   ├── launch
│   │   └── catch_turtle.launch.py
│   ├── package.xml
│   ├── resource
│   │   └── catch_turtle_bringup
│   └── setup.py
└── catch_turtle_interfaces
    ├── CMakeLists.txt
    ├── action
    │   └── CatchTarget.action
    └── package.xml
```

**最容易漏的一个文件**：`catch_turtle_bringup/resource/catch_turtle_bringup` 必须存在（空文件也行）。`ls -la src/catch_turtle_bringup/resource/` 确认；如果它不在，`touch src/catch_turtle_bringup/resource/catch_turtle_bringup` 补上。

### 1.2 行尾符自检（git 拉取场景下基本不用动）

```bash
cd ~/ROS2/ros2_ws
grep -rlI $'\r' src/ || echo "OK: 全是 LF"
```

预期：

- 大概率打印 `OK: 全是 LF` —— 直接进 1.3。
- 如果打印了若干文件名，说明里面混进了 CRLF（极少见，通常是某个开发者在 Windows 上动过文件）。修一下：

  ```bash
  sudo apt install -y dos2unix
  grep -rlI $'\r' src/ | xargs dos2unix
  grep -rlI $'\r' src/ || echo "OK: 全是 LF"   # 再确认一次
  ```

### 1.3 ROS2 / colcon 环境

```bash
source /opt/ros/humble/setup.bash
ros2 --version
which colcon
```

预期：

- `ros2 --version` 打印 humble 相关版本号。
- `which colcon` 打印一个非空路径（`/usr/bin/colcon` 或 `/opt/ros/humble/...`）。
- 如果 `which colcon` 啥也不打印：

  ```bash
  sudo apt install -y python3-colcon-common-extensions
  ```

### 1.4 GUI 显示（turtlesim 必须能开窗）

```bash
echo $DISPLAY
```

预期：非空（典型值 `:0` 或 `:1`）。

- 在 VM 桌面里开的终端：自然非空。
- 通过 `ssh` 连 VM：要么用 `ssh -X user@vm` 然后再开终端，要么干脆切到 VM 桌面里开终端，否则 `turtlesim_node` 启动会直接报错退出。

## 2. 阶段 B：一次编译（替代原计划里的多次 build）

只用 **1 个终端**。

```bash
cd ~/ROS2/ros2_ws
colcon build
source install/setup.bash
```

预期：

- `colcon build` 输出里出现 `Starting >>> catch_turtle_interfaces`、`Starting >>> catch_turtle_bringup`，最后一行 `Summary: 2 packages finished`，**没有红色 ERROR**。
- 工作区下生成 `build/`、`install/`、`log/`。

如果失败，**先看输出里第一条 ERROR**，按下面优先级排查：

1. `Could not find a package configuration file ... action_msgs`：环境没 source，重做 `source /opt/ros/humble/setup.bash` 再 build。
2. `setup.py` 报 `entry_points` 之类语法错：1.2 行尾符自检不彻底，对 `setup.py` 单独 `dos2unix` 一次。
3. `error: invalid command 'bdist_wheel'` / `setuptools` 老旧：`pip install --upgrade --user setuptools==65.7.0`（按 ROS2 Humble 的官方推荐版本）。
4. 其它：把第一条 ERROR 整段贴回去问。

通过后立刻做最小自检：

```bash
ros2 pkg list | grep catch_turtle
ros2 interface show catch_turtle_interfaces/action/CatchTarget
```

预期：

- 第 1 条恰好 2 行：`catch_turtle_bringup` 和 `catch_turtle_interfaces`。
- 第 2 条原样打印 `.action` 文件三段，含两条 `---`：

  ```text
  string target_name
  ---
  bool success
  string caught_name
  ---
  float32 distance_remaining
  ```

至此整套代码已经"装好"，剩下全是功能验证，不需要再 `colcon build`（除非你改了源码）。

## 3. 阶段 C：仿真 + 生成（对应原计划 4.2，3 终端）

**前置**：阶段 B 已通过。

同时打开 **3 个终端**，每个终端开头都做 0.1 节的开场白，然后按下面顺序启动。

### 终端 1（仿真器，必须最先起）

```bash
ros2 run turtlesim turtlesim_node
```

预期：

- 弹出蓝底 turtlesim 窗口，正中间是 `turtle1`。
- 终端打印 `Spawning turtle [turtle1] at x=[5.5], y=[5.5], theta=[0.0]`，之后没有持续刷屏。

### 终端 2（生成器）

```bash
ros2 run catch_turtle_bringup spawn_manager
```

预期：

- 启动时打印 `spawn_manager up; period=3.00s; first_name=turtle2`。
- 之后每 3 秒打印一行 `Spawned new turtle: turtleN`（N 从 2 起递增）。
- 终端 1 的 turtlesim 窗口里同步每 3 秒多一只海龟（位置随机）。

### 终端 3（旁路观察 topic）

等终端 2 已经至少 spawn 出 1~2 只海龟之后再执行：

```bash
ros2 topic list | grep pose
```

预期：列表里至少包含

```text
/turtle1/pose
/turtle2/pose
```

过几秒再执行一次同样的命令，列表会变长（出现 `/turtle3/pose`、`/turtle4/pose`…）。

**整体最终效果**：地图上每 3 秒多一只随机位置的海龟，`/turtleN/pose` topic 数量随时间线性增长。

**故障定位提示**：终端 2 报 `ModuleNotFoundError: No module named 'catch_turtle_bringup'` → 这个终端没 source；重新做 0.1 开场白。

**收尾**：3 个终端逐一 `Ctrl+C` 关闭。turtlesim 窗口会随终端 1 一起退出。

## 4. 阶段 D：手动抓一只（对应原计划 5.2，4 终端）

> **这是排错最关键的一步**：master_manager 完全建立在 `catch_target` 这个 action 之上，本阶段过不了后面全过不了。

**前置**：阶段 B 已通过。

同时打开 **4 个终端**，每个终端开头都做 0.1 节开场白，按以下顺序启动：

### 终端 1（仿真器）

```bash
ros2 run turtlesim turtlesim_node
```

预期：turtlesim 窗口弹出，`turtle1` 在中央。

### 终端 2（不断产生靶子）

```bash
ros2 run catch_turtle_bringup spawn_manager
```

预期：每 3 秒打印 `Spawned new turtle: turtleN`，地图上多一只海龟。**等到至少看到 `Spawned new turtle: turtle2` 之后再起终端 4**。

### 终端 3（Action Server）

```bash
ros2 run catch_turtle_bringup catch_executor
```

预期：启动时打印一行 `catch_executor ready, action: /catch_target`，之后保持安静（直到收到 goal）。

### 终端 4（手动下发一次抓捕 goal）

```bash
ros2 action send_goal /catch_target \
  catch_turtle_interfaces/action/CatchTarget \
  "{target_name: 'turtle2'}" --feedback
```

预期：

- 终端 4 立刻打印 `Waiting for an action server to become available...`，随后 `Sending goal:` + `Goal accepted with ID: ...`。
- 之后**每秒大约 20 行** `Feedback: distance_remaining: <数字>`，数字单调下降（中间偶有小抖动正常）。
- 同时 turtlesim 窗口里能肉眼看见 `turtle1` 朝 `turtle2` 移动（先转向、再前进）。
- 当距离首次小于 0.5（`catch_distance` 默认值）时，终端 4 打印：

  ```text
  Result:
    success: True
    caught_name: 'turtle2'
  Goal finished with status: SUCCEEDED
  ```

  并退出。
- 终端 3 在收到 goal 时打印 `Catch goal received: turtle2`，结束时打印 `Caught turtle2!`。

**故障定位提示**：

- 终端 4 长时间停在 `Waiting for an action server to become available...`：去终端 3 看是否打印过 `catch_executor ready`；没打印就是包没 source 或 entry point 缺失，回到阶段 B 重 build。
- `turtle1` 在 turtlesim 里**只转不走**：检查 `params.yaml` 里 `angle_tolerance` 是否被改得过小；或者 `linear_speed` 是否被改成了 0。
- `turtle1` **走过头来回振荡**：`max_angular_speed` 偏小或 `linear_speed` 偏大；恢复默认值。

**收尾**：4 个终端逐一 `Ctrl+C` 关闭。

## 5. 阶段 E：自动闭环（对应原计划 6.2，5 终端）

**前置**：阶段 D 已经能跑通。

同时打开 **5 个终端**，每个终端开头都做 0.1 节开场白，按以下顺序启动（顺序很重要：仿真器最先，master 最后）：

### 终端 1（仿真器）

```bash
ros2 run turtlesim turtlesim_node
```

### 终端 2（生产靶子）

```bash
ros2 run catch_turtle_bringup spawn_manager
```

### 终端 3（Action Server）

```bash
ros2 run catch_turtle_bringup catch_executor
```

### 终端 4（决策大脑）

```bash
ros2 run catch_turtle_bringup master_manager
```

预期：

- 启动时打印 `master_manager up`、`Tracking pose of turtle1`。
- 每发现一只新海龟就追加一行 `Tracking pose of turtleN`。
- 反复打印 `Dispatching catch goal: turtleN` → 不久后 `Chain updated -> ['turtle2']`、`['turtle2', 'turtle3']`…

### 终端 5（监听链条 topic）

```bash
ros2 topic echo /caught_chain
```

预期：每抓到一只海龟就打印一次 JSON 字符串，例如：

```text
data: '{"leader": "turtle1", "chain": ["turtle2"]}'
---
data: '{"leader": "turtle1", "chain": ["turtle2", "turtle3"]}'
---
```

`chain` 数组**只增不减**，永远不会出现重复名字。

**整体最终效果**：

- turtlesim 窗口里 `turtle1` 自动选最近的未抓海龟一只一只追，到 0.5 距离内就"抓住"（停下并切下一个目标，被抓的那只此后保持原地不动）。
- 终端 4 偶尔会有 `Preempting turtleA -> turtleB` 这种切换日志，那是滞回抢占在工作，属于正常。
- 持续运行 1 分钟以上不卡死、不重复抓同一只。

**故障定位提示**：

- `turtle1` 抓完一只后**不动了**：

  ```bash
  ros2 topic echo /caught_chain --once
  ros2 node info /master_manager
  ```

  看 chain 是不是确实在增长、master_manager 是不是还活着。
- 反复抓**同一只**：你的 `master_manager.py` 漏了 `_chain` 排除逻辑或 `mark_caught` 没调用。

**收尾**：5 个终端逐一 `Ctrl+C` 关闭。

## 6. 阶段 F：跟随成队（对应原计划 7.2）

**前置**：保持阶段 E 的 5 个终端继续运行。

再额外打开 **第 6 个终端**，开场白后执行：

```bash
ros2 run catch_turtle_bringup follower_manager
```

预期：

- 终端 6 启动时打印 `follower_manager up`，之后**几乎不再刷屏**。
- 每当 `turtle1` 抓到一只新海龟（终端 5 的 `chain` 增长一个名字），那只新海龟就**立刻开始尾随队尾**——先转向、再前进，最终保持约 0.8（`follow_distance`）的间距。
- `turtle1` 继续追下一只时，整条队伍像贪吃蛇一样跟着走。
- 队尾不会撞到队首，不会原地高频抖动。

**整体最终效果**：龟队随时间自动加长，链条 = 抓捕顺序，且每只都在跟前一只。

**故障定位提示**：

- 跟随者**原地抖动**：`follow_distance` 太小（默认 0.8 是合理值）；或 `angular_kp` 太大。
- 跟随者**完全不动**：检查终端 6 是不是漏 source；或 `/caught_chain` 没有正确订阅（`ros2 topic echo /caught_chain` 仍然能看到内容才算数据流到位）。

**收尾**：6 个终端逐一 `Ctrl+C` 关闭。

## 7. 阶段 G：一键启动（对应原计划 9.2，2 终端）

**前置**：阶段 F 之前的所有终端都已经 `Ctrl+C` 关闭，避免节点重名冲突。

### 终端 A（一键起整套系统）

```bash
ros2 launch catch_turtle_bringup catch_turtle.launch.py
```

预期：

- 屏幕开始混合打印 5 个节点的日志（每行前面带 `[turtlesim_node-1]` / `[spawn_manager-2]` / `[catch_executor-3]` / `[master_manager-4]` / `[follower_manager-5]` 前缀），其中能看到：
  - `[turtlesim_node-1] Spawning turtle [turtle1] ...`
  - `[catch_executor-3] catch_executor ready, action: /catch_target`
  - `[master_manager-4] master_manager up`
  - `[spawn_manager-2] Spawned new turtle: turtle2` ……
  - `[master_manager-4] Chain updated -> ['turtle2']` ……
- 同时弹出 turtlesim 窗口，`turtle1` 开始自动追、抓、带队。

### 终端 B（旁路检查，不改变系统状态）

等终端 A 已经稳定运行 10 秒后，依次执行：

```bash
ros2 node list
ros2 topic list
ros2 action list
```

预期：

- `ros2 node list` 至少包含

  ```text
  /catch_executor
  /follower_manager
  /master_manager
  /spawn_manager
  /turtlesim_node
  ```

- `ros2 topic list` 包含 `/caught_chain`、`/turtle1/cmd_vel`、`/turtle1/pose`、`/turtle2/pose`、`/turtle3/pose` 等。
- `ros2 action list` 恰好出现一行 `/catch_target`。

**整体最终效果**：

- 一句 `ros2 launch` 启动整套系统，无需手动 `ros2 run` 五次。
- 持续运行 ≥ 3 分钟不崩、不卡死、不重复抓同一只（与原计划第 13 节验收标准一致）。

**收尾**：在终端 A 按 `Ctrl+C`，5 个节点会一起退出，turtlesim 窗口关闭。

## 8. 验收标准（与原计划第 13 节一致）

- 一句 `ros2 launch catch_turtle_bringup catch_turtle.launch.py` 能起整套系统
- 每 3 秒地图上多一只海龟
- 主海龟自动追最近的未抓海龟，到 0.5 距离内判定抓到
- 抓到的海龟稳定地跟随它的前一只，链条持续增长
- 持续运行 3 分钟以上不崩、不卡死、不重复抓同一只
- `ros2 action list`、`ros2 topic list`、`ros2 node list` 输出符合设计
- 通过 `params.yaml` 调整参数无需改源码

## 9. 一份排错速查表

| 现象 | 大概率原因 | 处理 |
| --- | --- | --- |
| `colcon build` 报 `Could not find a package configuration file` | 当前 shell 没 `source /opt/ros/humble/setup.bash` | 先 source 再 build |
| `colcon build` 通过，但 `ros2 run catch_turtle_bringup ...` 报 `Package not found` | 当前 shell 没 `source install/setup.bash` | 重做 0.1 开场白 |
| `ros2 run ...` 报 `No executable found` | `setup.py` 的 `entry_points` 没注册或拼写错 | 看 `setup.py` 是否包含对应的 `xxx = catch_turtle_bringup.xxx:main` |
| `turtlesim_node` 启动闪退、终端无错或 `Cannot open display` | `$DISPLAY` 为空 | 在 VM 桌面终端跑，或 `ssh -X` |
| 终端 4 的 `send_goal` 一直 `Waiting for action server` | 终端 3 的 `catch_executor` 没起 / 没 source | 检查终端 3 |
| `turtle1` 抓到一只之后不再动 | `master_manager` 已退出 / 抢占逻辑卡死 | `ros2 node list` 看 master_manager 在不在；不在就重启 |
| 反复抓同一只 | 代码里没 `mark_caught` 或 `chain` 排除丢失 | 比对 `master_manager.py` 与原计划 6.1 节代码 |
| 跟随者原地抖动 | `follow_distance` 太小 或 `angular_kp` 太大 | 调 `params.yaml`（注意是 `install/` 下的版本被加载，改源 yaml 后需 `colcon build` 或直接改 `install/.../config/params.yaml` 临时验证） |
| 改了 `params.yaml` 不生效 | 没重新 build；launch 加载的是 `install/share/.../params.yaml` | `colcon build --packages-select catch_turtle_bringup` |
