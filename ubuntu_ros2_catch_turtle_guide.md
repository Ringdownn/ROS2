# Ubuntu 上完成 Catch Turtle All 项目的详细实施文档

这份文档面向“从零开始在 Ubuntu 上完成 `Catch Turtle All` 课程项目”的场景编写，重点关注**环境安装、工程搭建、开发步骤、联调步骤和验收步骤**，先**忽略具体代码实现**。  
你可以把它理解成一份“照着做就能把项目完整搭起来”的执行手册。

## 1. 文档目标

完成这个项目，你最终需要做到以下几点：

- 在 `turtlesim` 中运行一个持续工作的 ROS2 系统
- 每隔 `3` 秒随机生成一只新海龟
- 主海龟自动寻找并追捕最近的海龟
- 被抓到的海龟加入队列，并依次跟随前一只海龟
- 所有节点可以通过一个 `launch` 文件统一启动
- 可以完成演示、录视频、写报告和提交源代码

这份文档默认采用以下环境：

- `Ubuntu 22.04`
- `ROS2 Humble`
- `Python 3`
- 使用 `rclpy` 开发

如果你使用的是 `Ubuntu 24.04`，通常应改用 `ROS2 Jazzy`，整体流程相同，但安装命令会略有不同。

## 2. 项目总览

这个项目建议拆成以下几个功能模块：

- `turtlesim_node`
  - 仿真环境，显示海龟、发布位姿、接收速度控制、提供生成服务
- `spawn_manager`
  - 负责每 `3` 秒生成新海龟
- `master_manager`
  - 负责选择最近目标，并发起抓捕任务
- `catch_executor`
  - 负责执行主海龟的抓捕动作
- `follower_manager`
  - 负责让已抓海龟形成跟随链
- `launch file`
  - 负责统一启动整个系统

推荐的 ROS2 包结构：

- `catch_turtle_interfaces`
  - 放自定义 `action`
- `catch_turtle_bringup`
  - 放 Python 节点、launch 文件、配置文件

## 3. 完成项目的总步骤

整个项目建议按下面的顺序完成：

1. 安装 Ubuntu 所需基础环境
2. 安装 ROS2
3. 安装 `turtlesim` 和开发依赖
4. 创建 ROS2 工作区
5. 创建项目包结构
6. 先验证 `turtlesim` 能正常运行
7. 先完成“生成海龟”的能力验证
8. 再完成“主海龟追最近目标”的能力验证
9. 再加入 `action` 架构
10. 最后加入“海龟链跟随”
11. 编写统一启动文件
12. 完整联调、录视频、写报告、打包提交

不要一开始就把所有功能同时写出来。这个项目最稳妥的方法是**按功能分阶段推进**。

## 4. Ubuntu 环境准备

### 4.1 确认 Ubuntu 版本

打开终端运行：

```bash
lsb_release -a
```

你最好看到的是：

- `Ubuntu 22.04`

如果不是 `22.04`：

- `20.04` 上更常见的是 `ROS2 Foxy`，不建议用于新作业
- `24.04` 上更适合 `ROS2 Jazzy`

### 4.2 更新系统

先更新系统软件源和已安装的软件包：

```bash
sudo apt update
sudo apt upgrade -y
```

### 4.3 安装常用工具

建议安装这些基础工具：

```bash
sudo apt install -y \
  curl \
  gnupg \
  lsb-release \
  build-essential \
  git \
  wget \
  python3-pip \
  python3-colcon-common-extensions \
  python3-rosdep \
  python3-vcstool
```

这些工具的作用：

- `git`：管理工程
- `pip`：安装 Python 包
- `colcon`：构建 ROS2 工作区
- `rosdep`：自动安装 ROS 依赖
- `vcstool`：管理多个仓库时有用

## 5. 安装 ROS2 Humble

### 5.1 添加 ROS2 软件源

```bash
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository universe
```

导入 ROS2 的 GPG key：

```bash
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg
```

添加 ROS2 软件源：

```bash
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
```

更新软件源：

```bash
sudo apt update
```

### 5.2 安装 ROS2 本体

建议安装桌面完整版：

```bash
sudo apt install -y ros-humble-desktop
```

如果你的机器资源有限，也可以只装基础版，但做课程项目时更推荐 `desktop`。

### 5.3 配置环境变量

先临时生效：

```bash
source /opt/ros/humble/setup.bash
```

再写入 `~/.bashrc`，以后每次打开终端自动生效：

```bash
echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

### 5.4 初始化 rosdep

```bash
sudo rosdep init
rosdep update
```

如果这里报网络问题，可以稍后重试，或者检查网络环境。

## 6. 安装本项目需要的 ROS2 依赖

安装课程项目会用到的核心包：

```bash
sudo apt install -y \
  ros-humble-turtlesim \
  ros-humble-geometry-msgs \
  ros-humble-std-msgs \
  ros-humble-action-msgs \
  ros-humble-launch \
  ros-humble-launch-ros \
  ros-humble-rosidl-default-generators
```

这些包分别用于：

- `turtlesim`
  - 运行海龟仿真
- `geometry_msgs`
  - 发布速度消息 `Twist`
- `std_msgs`
  - 传递简单状态数据
- `action_msgs`
  - 支持 `action`
- `launch` 与 `launch_ros`
  - 编写和启动 `launch file`
- `rosidl_default_generators`
  - 生成自定义接口

## 7. 验证 ROS2 和 turtlesim 是否正常

### 7.1 启动 turtlesim

```bash
ros2 run turtlesim turtlesim_node
```

如果一切正常，你会看到一个海龟窗口。

### 7.2 启动键盘控制

另开一个终端，先执行：

```bash
source /opt/ros/humble/setup.bash
```

再运行：

```bash
ros2 run turtlesim turtle_teleop_key
```

如果你能用方向键控制海龟，说明：

- ROS2 已安装成功
- `turtlesim` 已安装成功
- 话题通信工作正常

### 7.3 查看 ROS2 图中的对象

另开终端执行：

```bash
ros2 node list
ros2 topic list
ros2 service list
```

你应该能看到与 `turtlesim` 相关的节点、话题和服务。

这是后面调试项目时非常重要的基本能力。

## 8. 创建 ROS2 工作区

### 8.1 创建工作区目录

建议在用户主目录下创建工作区：

```bash
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws
```

### 8.2 初始化构建

第一次可以直接试构建一次：

```bash
colcon build
```

构建完成后，工作区下通常会出现：

- `build/`
- `install/`
- `log/`

### 8.3 配置工作区环境

以后每次进入工作区开发前，要执行：

```bash
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash
```

为了方便，也可以把工作区环境写入 `~/.bashrc`，但建议在工作区较稳定后再写。

## 9. 创建项目包结构

建议建立两个包：

- `catch_turtle_interfaces`
- `catch_turtle_bringup`

这样做的原因：

- 接口和逻辑分离，更符合 ROS2 规范
- 自定义 `action` 更容易管理
- 后期维护和汇报更清晰

### 9.1 创建接口包

进入工作区源码目录：

```bash
cd ~/ros2_ws/src
```

创建接口包时，建议使用 `ament_cmake`：

```bash
ros2 pkg create catch_turtle_interfaces --build-type ament_cmake
```

后续你需要在这个包里放：

- `action/CatchTarget.action`
- `package.xml`
- `CMakeLists.txt`

### 9.2 创建主功能包

继续在 `src` 下创建 Python 包：

```bash
ros2 pkg create catch_turtle_bringup --build-type ament_python
```

这个包里后续要放：

- `spawn_manager.py`
- `master_manager.py`
- `catch_executor.py`
- `follower_manager.py`
- `launch/catch_turtle.launch.py`
- `config/params.yaml`

## 10. 先搭建目录，再开始实现

在真正写节点逻辑前，先把目录规范搭起来。建议最终结构如下：

```text
~/ros2_ws/
├── src/
│   ├── catch_turtle_interfaces/
│   │   ├── action/
│   │   │   └── CatchTarget.action
│   │   ├── CMakeLists.txt
│   │   └── package.xml
│   └── catch_turtle_bringup/
│       ├── catch_turtle_bringup/
│       │   ├── __init__.py
│       │   ├── spawn_manager.py
│       │   ├── master_manager.py
│       │   ├── catch_executor.py
│       │   ├── follower_manager.py
│       │   ├── turtle_registry.py
│       │   └── utils.py
│       ├── launch/
│       │   └── catch_turtle.launch.py
│       ├── config/
│       │   └── params.yaml
│       ├── resource/
│       │   └── catch_turtle_bringup
│       ├── setup.py
│       └── package.xml
├── build/
├── install/
└── log/
```

在这个阶段，你的目标不是写完代码，而是把：

- 包名定好
- 文件名定好
- 职责定好
- 构建方式定好

## 11. 明确每个节点的职责，再开始编码

在动手前，先把每个节点要做什么完全想清楚。

### 11.1 `spawn_manager`

你要完成的不是“随机函数”本身，而是完整的“生成流程”：

- 建立一个定时器
- 每 `3` 秒触发一次
- 生成一个随机位置
- 调用 `/spawn` 服务
- 给新海龟命名
- 保证新海龟能被系统后续追踪

### 11.2 `master_manager`

你要实现的是“决策中心”，而不是简单控制器：

- 维护所有海龟的位置
- 区分哪些海龟已抓到、哪些还没抓到
- 始终找到最近目标
- 将抓捕任务发送给执行节点
- 抓捕成功后更新链条

### 11.3 `catch_executor`

这是运动执行层：

- 接收“抓哪只海龟”的任务
- 控制主海龟移动
- 持续输出抓捕反馈
- 到达目标阈值后报告抓捕成功

### 11.4 `follower_manager`

这是链式跟随层：

- 接收“已抓海龟链”信息
- 让第一只跟随主海龟
- 让后续每只跟随前一只
- 保持链条稳定，不要剧烈抖动

### 11.5 `launch file`

这是最后把系统整合起来的关键：

- 启动 `turtlesim_node`
- 启动 4 个自定义节点
- 加载参数文件
- 保证整套系统一条命令就能启动

## 12. 开发顺序建议

这个项目最重要的不是“功能多快写完”，而是“每一步都能验证”。

推荐按下面顺序推进：

### 阶段 1：只验证 turtlesim

你要确认：

- 海龟窗口能打开
- 海龟可以被键盘控制
- ROS2 节点、话题、服务都能查到

这一阶段没问题后，再进入下一步。

### 阶段 2：只实现海龟生成流程

你要先单独验证：

- 能调用 `/spawn`
- 能按固定周期生成新海龟
- 新海龟会出现在地图上
- 名字不会冲突

只要“生成成功”，这一阶段就算通过。

### 阶段 3：只实现主海龟追踪单个目标

此阶段先不要考虑多个目标，也不要考虑链条。

你只需要验证：

- 主海龟能读取自己的 `pose`
- 主海龟能读取目标海龟的 `pose`
- 主海龟能朝着目标转向
- 主海龟能移动到目标附近

这个阶段的目标是证明“追捕运动控制是可行的”。

### 阶段 4：实现“最近目标选择”

这时再加入多个新海龟。

你要验证：

- 主海龟知道有哪些候选目标
- 能正确计算距离
- 每次都追最近的一只
- 抓到后不会重复追同一只

### 阶段 5：把抓捕过程改造成 Action

不要一开始就写 `action`，先验证追捕逻辑可行，再把它抽象成 `Action Server` 和 `Action Client`。

这一阶段你要完成：

- 定义 `CatchTarget.action`
- `master_manager` 作为 `Action Client`
- `catch_executor` 作为 `Action Server`
- 能发送目标、接收反馈、接收结果

### 阶段 6：加入跟随链

当抓捕流程跑通后，再做跟随控制。

你要逐步验证：

- 第一只被抓到的海龟能跟随主海龟
- 第二只被抓到的海龟能跟随第一只
- 链条扩展时不会乱套

### 阶段 7：加入 launch 和参数化

最后再统一整理：

- 所有节点是否都能通过 `launch` 启动
- 参数是否都集中放到 `params.yaml`
- 各个文件路径是否正确
- 启动顺序是否合理

## 13. 每个阶段都要做的验证动作

每完成一个阶段，都建议做一次“最小验证”。

### 13.1 节点验证

```bash
ros2 node list
```

检查：

- 节点是否真的启动了
- 节点名是否符合预期

### 13.2 话题验证

```bash
ros2 topic list
ros2 topic echo /turtle1/pose
```

检查：

- 话题是否存在
- 位姿数据是否持续更新

### 13.3 服务验证

```bash
ros2 service list
ros2 service type /spawn
```

检查：

- `/spawn` 是否存在
- 服务类型是否正确

### 13.4 Action 验证

```bash
ros2 action list
ros2 action info /catch_target
```

检查：

- action 是否已经注册
- client 和 server 是否正常存在

### 13.5 构建验证

每次修改包结构或依赖后，都建议在工作区根目录执行：

```bash
cd ~/ros2_ws
source /opt/ros/humble/setup.bash
colcon build
source install/setup.bash
```

## 14. 参数整理建议

虽然你现在先不写具体代码，但建议提前规划参数文件，这样后面会轻松很多。

建议把下面这些参数独立出来：

- 生成周期
- 地图边界
- 生成安全边距
- 主海龟线速度
- 主海龟角速度
- 抓捕判定距离
- 跟随目标距离
- 跟随线速度
- 跟随角速度

这样做的好处：

- 后期调试不需要反复改代码
- 录制演示视频时可以快速调整运动效果
- 报告中更容易说明系统可配置性

## 15. 建议的调试方式

这个项目非常适合边做边调试，不适合写完再一次性跑。

建议采用以下调试顺序：

1. 只跑 `turtlesim`
2. 再跑 `spawn_manager`
3. 再跑主海龟控制节点
4. 再跑 `action`
5. 最后跑 `follower_manager`

调试时重点观察：

- 海龟是否真的被生成
- 主海龟是否真的朝最近目标移动
- 抓到后状态是否更新
- 新抓到的海龟是否加入链条
- 链条是否稳定

## 16. 常见问题和排查思路

### 16.1 找不到 ROS2 命令

现象：

- 输入 `ros2` 提示命令不存在

排查：

- 是否执行了 `source /opt/ros/humble/setup.bash`
- 是否正确安装了 `ros-humble-desktop`

### 16.2 turtlesim 启动失败

现象：

- 执行 `ros2 run turtlesim turtlesim_node` 失败

排查：

- 是否安装了 `ros-humble-turtlesim`
- 图形界面是否正常
- 是否在正确的 ROS2 环境中执行

### 16.3 colcon build 失败

排查重点：

- `package.xml` 依赖是否缺失
- `setup.py` 或 `CMakeLists.txt` 是否配置错误
- 自定义 `action` 是否放在正确目录
- 是否缺少 `rosidl_default_generators`

### 16.4 Action 不可见

排查：

- `Action Server` 是否真的启动
- 是否已经 `source install/setup.bash`
- 接口包是否成功编译

### 16.5 新海龟生成了，但系统没有追踪

排查：

- 是否订阅到了新海龟的 `pose`
- 是否把新海龟加入了内部状态表
- 是否在目标筛选逻辑中漏掉了它

### 16.6 跟随链不稳定

排查：

- 跟随距离是否过小
- 速度是否过快
- 角度误差是否做了归一化
- 是否每只海龟都跟对了 leader

## 17. 最终联调步骤

当所有模块都准备好后，按下面顺序进行完整联调：

1. 在工作区根目录执行构建
2. `source` ROS2 和工作区环境
3. 用 `launch` 启动整套系统
4. 观察是否成功启动所有节点
5. 观察是否每 `3` 秒生成新海龟
6. 观察主海龟是否优先追最近目标
7. 观察抓到后海龟是否加入链条
8. 持续运行几分钟，确认系统不会很快失控

联调通过的最低标准：

- 系统能长期运行
- 没有明显的重复抓捕错误
- 跟随链会持续增长
- 启动方式统一

## 18. 演示视频准备建议

老师要求录视频时，建议按下面顺序拍摄：

1. 展示团队成员
2. 展示运行设备
3. 展示打开终端和进入工作区
4. 展示启动命令
5. 展示海龟不断生成
6. 展示主海龟自动追最近目标
7. 展示已抓海龟形成链条
8. 展示系统持续运行效果

录制前建议先检查：

- 桌面整洁
- 终端字体大小合适
- 系统已经编译通过
- 运动速度不要太快，方便展示

## 19. 项目报告准备建议

你最终的报告可以按下面结构写：

1. 项目目标
2. 系统整体架构
3. 节点设计
4. 话题、服务、action 关系
5. 关键功能说明
6. 调试和测试过程
7. 运行结果展示
8. 分工说明

报告里建议重点强调：

- 为什么把系统拆成多个节点
- 为什么用 `service` 做生成
- 为什么用 `topic` 做位姿和速度通信
- 为什么用 `action` 做抓捕任务

## 20. 最终提交前检查清单

在提交前逐项检查：

- ROS2 工作区可以成功构建
- 所有依赖都已安装
- `launch` 可以一键启动
- 生成、抓捕、跟随链功能全部可演示
- 视频已录制完成
- 报告已写完
- 小组成员信息和分工说明已整理

## 21. 一条最推荐的实施路线

如果你想用最稳的方法推进，建议严格按下面路线做：

1. 安装 `Ubuntu 22.04`
2. 安装 `ROS2 Humble`
3. 安装 `turtlesim` 和构建工具
4. 创建 `~/ros2_ws`
5. 创建 `catch_turtle_interfaces`
6. 创建 `catch_turtle_bringup`
7. 先验证 `turtlesim`
8. 再完成海龟生成
9. 再完成主海龟追目标
10. 再改造成 `action`
11. 再完成跟随链
12. 最后整理 `launch`、参数、视频和报告

只要你按这个顺序做，这个项目是可以稳定完成的。

## 22. 下一步建议

这份文档解决的是“步骤和路线”问题。  
当你准备进入真正实现阶段时，最自然的下一步是：

- 先让我帮你生成两个 ROS2 包的完整模板
- 再让我帮你写每个节点的代码骨架
- 最后再逐个实现节点逻辑和联调

如果你愿意，我下一步可以继续直接给你一份：

- `Ubuntu + ROS2 Humble` 下的项目初始化命令清单
- 两个 ROS2 包的完整目录模板
- 每个节点第一版最小可运行骨架
