# Catch Turtle All 整体实现方案

下面给你一套适合这个作业的整体实现方案。目标是既满足题目要求，又方便你后续直接拆成 ROS2 代码来做。

## 总体思路

- 用 `turtlesim` 作为仿真环境。
- 用一个节点负责定时生成新海龟。
- 用一个节点负责主海龟的目标选择和抓捕调度。
- 用一个节点负责具体执行抓捕动作，体现 `Action Server`。
- 用一个节点负责已抓海龟的链式跟随。
- 用一个 `launch` 文件统一启动所有节点，形成持续运行的系统。

整个系统的核心流程是：

```text
生成海龟 -> 维护所有海龟位置 -> 选择最近目标 -> 主海龟追捕 -> 标记已抓到 -> 加入跟随链 -> 继续抓下一只
```

## 整体实现方案

### 1. 系统分层

- 仿真层：`turtlesim_node`
  - 提供海龟显示、位置发布、速度控制、生成服务。
- 任务管理层：`master_manager`
  - 管理“当前有哪些海龟可抓”，选择最近目标，发起抓捕任务。
- 执行控制层：`catch_executor`
  - 控制主海龟转向、前进、接近目标，直到判定抓到。
- 环境生成层：`spawn_manager`
  - 定时生成海龟。
- 编队跟随层：`follower_manager`
  - 让被抓到的海龟依次跟随前一只海龟，形成链条。

### 2. 为什么这样拆

- 职责清晰，方便调试。
- 符合 ROS2 的通信模式：
  - `service` 适合生成海龟
  - `topic` 适合持续传输位置和速度
  - `action` 适合“抓某个目标”这种长时间任务
- 后续写报告时也容易说明系统架构。

## 节点设计

### 1. `turtlesim_node`

这是系统提供的仿真节点，不需要你自己写。

#### 作用

- 显示所有海龟
- 提供 `/spawn` 服务生成新海龟
- 发布每只海龟的 `/pose`
- 接收每只海龟的 `/cmd_vel`

#### 你会用到的接口

- `service`: `/spawn`
- `topic`: `/<turtle_name>/pose`
- `topic`: `/<turtle_name>/cmd_vel`

### 2. `spawn_manager`

这个节点负责不断往地图里添加新的海龟。

#### 职责

- 每隔 `3 秒` 生成一只新海龟
- 随机生成 `(x, y, theta)`
- 为每只海龟命名，例如 `turtle2`、`turtle3`、`turtle4`
- 把新生成的海龟加入系统可追踪对象中

#### 需要实现的功能

- 创建一个定时器 `timer`
- 调用 `turtlesim` 的 `/spawn` 服务
- 生成随机坐标时注意边界，避免贴边太近
- 可选：避免与已有海龟过近，减少刚生成就重叠

#### 输入

- 无

#### 输出

- 调用 `/spawn` 服务生成海龟

#### 建议参数

- `spawn_period`: 3.0
- `x_min`, `x_max`, `y_min`, `y_max`
- `safe_margin`

### 3. `master_manager`

这个节点是系统“大脑”，负责决策。

#### 职责

- 维护当前所有海龟的状态
- 判断哪些海龟是“未抓到的目标”
- 选择距离主海龟最近的一只作为抓捕目标
- 通过 `Action Client` 发起抓捕任务
- 接收抓捕结果并更新“已抓海龟链”

#### 需要实现的功能

- 订阅主海龟和所有目标海龟的 `pose`
- 维护一个海龟状态表，例如：
  - 海龟名
  - 当前坐标
  - 是否已抓到
  - 是否正在被追捕
- 周期性计算最近目标
- 如果当前没有抓捕任务，就挑选最近目标发送 `action goal`
- 如果当前目标消失或已抓到，就重新选目标
- 抓到后发布链条更新消息给 `follower_manager`

#### 输入

- `/<turtle_name>/pose`
- `catch action` 的结果和反馈

#### 输出

- 向 `catch_executor` 发送抓捕目标
- 向 `follower_manager` 发布已抓海龟链信息

#### 核心算法

- 遍历所有未抓海龟
- 计算主海龟与它们的欧氏距离
- 选最近的一只

#### 建议内部状态

```text
master_pose
all_turtles = {
  turtle2: {pose, caught, active},
  turtle3: {pose, caught, active},
  ...
}
caught_chain = [turtle2, turtle5, turtle4]
current_target = turtle6
```

### 4. `catch_executor`

这个节点负责真正控制主海龟去抓目标，建议做成 `Action Server`。

#### 职责

- 接收“抓某只海龟”的 goal
- 控制 `turtle1` 朝目标移动
- 到达判定阈值后返回成功结果
- 持续反馈“距离还剩多少”

#### 需要实现的功能

- 实现一个 `CatchTarget.action`
- 订阅主海龟位置和目标海龟位置
- 根据目标位置计算：
  - 目标方向角
  - 角度误差
  - 距离误差
- 发布 `turtle1/cmd_vel`
- 控制逻辑通常分两步：
  - 先转向
  - 再前进
- 距离足够近时，认为抓到

#### 输入

- `CatchTarget` goal
- `/turtle1/pose`
- `/<target>/pose`

#### 输出

- `/turtle1/cmd_vel`
- `action feedback/result`

#### 建议控制逻辑

- 若角度误差大，优先转向
- 若朝向对准后，前进
- 到目标距离小于阈值，例如 `0.5`，判定抓到

#### 建议参数

- `distance_tolerance`
- `linear_speed`
- `angular_speed`
- `angle_tolerance`

### 5. `follower_manager`

这个节点负责实现“海龟链”。

#### 职责

- 维护已抓到海龟的顺序
- 让每只海龟跟随自己前一只海龟
- 形成稳定链条

#### 链条规则

- 第一只被抓到的海龟跟随 `turtle1`
- 第二只跟随第一只
- 第三只跟随第二只
- 以此类推

#### 需要实现的功能

- 接收 `master_manager` 发布的链条顺序
- 订阅链条中所有海龟的 `pose`
- 为每只 follower 计算速度控制
- 给每只 follower 发布对应 `cmd_vel`

#### 输入

- 已抓海龟链，例如 `[turtle2, turtle5, turtle4]`
- 所有链条海龟的 `pose`

#### 输出

- `/turtle2/cmd_vel`
- `/turtle5/cmd_vel`
- `/turtle4/cmd_vel`
- 等等

#### 跟随控制逻辑

- follower 的目标不是固定点，而是“前一只海龟的当前位置”
- 计算 follower 到 leader 的距离和角度
- 若太远则前进
- 若方向偏差过大则先转向
- 若已经很近则减速或停止

#### 建议参数

- `follow_distance`
- `follow_linear_speed`
- `follow_angular_speed`

## 节点之间的通信关系

### Topics

- `/<turtle_name>/pose`
  - 来源：`turtlesim_node`
  - 去向：`master_manager`、`catch_executor`、`follower_manager`
- `/turtle1/cmd_vel`
  - 来源：`catch_executor`
  - 去向：`turtlesim_node`
- `/turtleX/cmd_vel`
  - 来源：`follower_manager`
  - 去向：`turtlesim_node`
- `/caught_chain`
  - 来源：`master_manager`
  - 去向：`follower_manager`

### Services

- `/spawn`
  - 来源：`spawn_manager`
  - 去向：`turtlesim_node`

### Actions

- `/catch_target`
  - Client：`master_manager`
  - Server：`catch_executor`

## 推荐的 Action 定义

```action
string target_name
---
bool success
string caught_name
---
float32 distance_remaining
```

#### 含义

- Goal：要抓哪只海龟
- Result：是否抓到、抓到的是谁
- Feedback：当前距离目标还有多远

## 整体运行流程

### 阶段 1：启动

- `launch` 启动 `turtlesim_node`
- 启动 `spawn_manager`
- 启动 `master_manager`
- 启动 `catch_executor`
- 启动 `follower_manager`

### 阶段 2：生成目标

- `spawn_manager` 每 `3 秒` 生成一只新海龟
- 新海龟开始发布自己的 `pose`

### 阶段 3：目标选择

- `master_manager` 收到所有海龟位置
- 去掉已经抓到的海龟
- 从剩余目标中找最近的一只

### 阶段 4：执行抓捕

- `master_manager` 发送 `CatchTarget` goal
- `catch_executor` 控制 `turtle1` 追过去
- 抓到后返回成功结果

### 阶段 5：加入链条

- `master_manager` 更新 `caught_chain`
- `follower_manager` 让新海龟加入队尾跟随

### 阶段 6：循环继续

- `master_manager` 再选下一只最近目标
- 系统不断循环运行

## 建议的控制算法

### 主海龟抓捕算法

- 输入：主海龟位置 `(x_m, y_m, theta_m)`，目标位置 `(x_t, y_t)`
- 计算：
  - `dx = x_t - x_m`
  - `dy = y_t - y_m`
  - `target_angle = atan2(dy, dx)`
  - `angle_error = normalize(target_angle - theta_m)`
  - `distance = sqrt(dx^2 + dy^2)`

#### 控制规则

- 若 `abs(angle_error)` 大于阈值，先旋转
- 否则前进
- 若 `distance < catch_threshold`，判定抓到

### 跟随算法

- follower 把前一只海龟当作 leader
- 目标不是完全重合，而是保持一个短距离
- 距离过大则前进，距离足够近则停止或减速

## 项目结构建议

推荐拆成两个 ROS2 包。

```text
ros2_ws/
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

## 每个文件建议放什么

### `CatchTarget.action`

- 定义抓捕任务的 goal/result/feedback

### `spawn_manager.py`

- 定时器
- 随机坐标生成
- `/spawn` service client

### `master_manager.py`

- 维护海龟总表
- 选择最近目标
- action client
- 发布已抓链信息

### `catch_executor.py`

- action server
- 主海龟控制逻辑
- 订阅位姿
- 发布 `turtle1/cmd_vel`

### `follower_manager.py`

- 维护链条
- 为每个 follower 计算速度
- 发布 follower 的 `cmd_vel`

### `turtle_registry.py`

- 可选
- 封装海龟状态管理
- 存储：
  - name
  - pose
  - caught
  - active

### `utils.py`

- 角度归一化
- 距离计算
- 速度限幅
- 通用数学函数

### `params.yaml`

- 集中配置参数，例如：
  - 生成周期
  - 抓捕距离阈值
  - 跟随距离
  - 线速度和角速度

### `catch_turtle.launch.py`

- 启动所有节点
- 加载参数
- 启动 `turtlesim_node`

## 建议参数设计

```yaml
spawn_manager:
  ros__parameters:
    spawn_period: 3.0
    x_min: 1.0
    x_max: 10.0
    y_min: 1.0
    y_max: 10.0

catch_executor:
  ros__parameters:
    linear_speed: 1.5
    angular_speed: 3.0
    catch_distance: 0.5
    angle_tolerance: 0.1

follower_manager:
  ros__parameters:
    follow_distance: 0.8
    linear_speed: 1.2
    angular_speed: 2.5
```

## 开发顺序建议

- 第一步：先单独跑 `turtlesim`
- 第二步：完成 `spawn_manager`
- 第三步：完成主海龟手动追最近目标，不用 action
- 第四步：把追目标逻辑改造成 `action server/client`
- 第五步：加入 `follower_manager`
- 第六步：做 launch 和参数整理
- 第七步：录视频、写报告

## 实现时最容易出问题的点

- 新生成海龟后，没有及时订阅到它的 `pose`
- 主海龟重复抓同一只海龟
- `Action` 正在执行时，新目标出现导致状态混乱
- 跟随链控制过激，海龟抖动严重
- follower 和 leader 距离太近，造成碰撞或绕圈
- 角度没有做归一化，导致转向错误

## 最推荐的简化版本

如果你想先做一个能跑通、容易展示的版本，可以用下面的策略：

- 不实现复杂全局路径规划
- 用“转向 + 直线前进”的局部控制就够了
- 每次只抓最近目标
- 被抓到后不删除海龟，只切换成 follower 模式
- follower 用简单比例控制跟随 leader

这个方案已经足够满足作业要求。

## 一句话总结

- `spawn_manager` 负责“生”
- `master_manager` 负责“想”
- `catch_executor` 负责“抓”
- `follower_manager` 负责“跟”
- `launch` 负责“一键跑起来”
