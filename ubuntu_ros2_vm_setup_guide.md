# Ubuntu 22.04 + ROS2 Humble 虚拟机完整搭建指南

> 本文档面向 Catch Turtle All 项目，从零开始搭建虚拟机环境。
>
> 适用环境：macOS + UTM + Ubuntu 22.04 Server ARM64 + SSH 连接

---

## 目录

1. [UTM 虚拟机创建](#1-utm-虚拟机创建)
2. [Ubuntu 系统安装](#2-ubuntu-系统安装)
3. [SSH 连接配置](#3-ssh-连接配置)
4. [虚拟机首次配置](#4-虚拟机首次配置)
5. [ROS2 Humble 安装](#5-ros2-humble-安装)
6. [项目代码拉取与构建](#6-项目代码拉取与构建)
7. [功能验证](#7-功能验证)
8. [常见问题排查](#8-常见问题排查)

---

## 1. UTM 虚拟机创建

### 1.1 下载所需软件

1. **UTM**（虚拟机软件）
   ```
   https://mac.getutm.app/
   ```

2. **Ubuntu 22.04 Server ARM64 ISO**
   ```
   https://mirrors.tuna.tsinghua.edu.cn/ubuntu-cdimage/ubuntu-server/jammy/daily-live/current/jammy-live-server-arm64.iso
   ```
   
   文件名应包含 `arm64`，例如：
   ```
   ubuntu-22.04.5-live-server-arm64+largemem.iso
   ```

### 1.2 创建虚拟机

1. 打开 UTM，点击 **"创建新虚拟机"**
2. 选择 **"虚拟化" (Virtualize)** → **"Linux"**
3. 选择下载好的 ISO 文件
4. 配置硬件：
   - **内存**：4096 MB (4GB)，推荐 8192 MB (8GB)
   - **CPU 核心**：4 核
   - **硬盘**：50 GB
5. 完成创建，启动虚拟机

### 1.3 安装 Ubuntu

1. 启动后进入 GRUB 菜单，选择 **"Try or Install Ubuntu Server"**
2. 选择语言：**English** 或 **中文(简体)**
3. 键盘布局：默认即可
4. 安装类型：**Ubuntu Server**
5. 网络配置：选择 DHCP 自动获取（记录显示的 IP 地址）
6. 代理配置：留空，直接继续
7. 镜像地址：改为国内镜像加速
   ```
   https://mirrors.tuna.tsinghua.edu.cn/ubuntu
   ```
8. 存储配置：使用整个磁盘，确认分区
9. 用户信息：
   - 姓名：yourname
   - 服务器名：ubuntu-ros2
   - 用户名：yourname
   - 密码：设置强密码
10. SSH 配置：**勾选安装 OpenSSH 服务器**
11. 特色服务器快照：不需要，直接继续
12. 等待安装完成
13. 安装完成后选择 **"Reboot Now"**
14. 重启前在 UTM 设置中**移除 ISO 文件**（防止再次从光盘启动）

---

## 2. Ubuntu 系统安装

### 2.1 首次登录

重启后进入登录界面，输入用户名和密码登录。

### 2.2 查看 IP 地址

```bash
ip addr show
```

找到 `enp0s1` 或类似网卡的 IP，例如：
```
inet 192.168.64.2/24
```

记录这个 IP，后续 SSH 连接需要用到。

---

## 3. SSH 连接配置

### 3.1 macOS 安装 XQuartz（用于图形转发）

```bash
brew install --cask xquartz
```

安装后**重启 macOS**。

### 3.2 Tabby 配置 SSH 连接

1. 打开 Tabby，点击 **"Profiles & connections"**（或按 `Cmd+Shift+E`）
2. 点击 **"New profile"** → **"SSH connection"**
3. 填写连接信息：
   - **Name**: Ubuntu-ROS2
   - **Host**: `192.168.64.2`（虚拟机 IP）
   - **Port**: `22`
   - **User**: 你的用户名
4. 配置 X11 转发：
   - 找到 **"Advanced"** 或 **"SSH"** 选项卡
   - 勾选 **"Enable X11 forwarding"**
   - 或在 "Custom SSH options" 中添加 `-X`
5. 点击 **"Save"**
6. 双击连接，输入密码登录

### 3.3 验证 SSH 连接

登录后测试：

```bash
# 测试基础连接
whoami
hostname

# 测试 X11 转发（需要安装 ROS2 后测试）
# 见第 5.7 节
```

---

## 4. 虚拟机首次配置

SSH 连接成功后，在虚拟机中执行以下配置：

### 4.1 更新系统

```bash
sudo apt update
sudo apt upgrade -y
```

### 4.2 安装基础工具

```bash
sudo apt install -y \
  curl \
  wget \
  git \
  vim \
  net-tools \
  htop \
  tree \
  unzip
```

### 4.3 设置时区

```bash
sudo timedatectl set-timezone Asia/Shanghai
date
```

### 4.4 查看系统信息

```bash
lsb_release -a
uname -a
```

### 4.5 配置静态 IP（可选）

如果希望 IP 固定不变：

```bash
sudo nano /etc/netplan/00-installer-config.yaml
```

修改为静态 IP：
```yaml
network:
  version: 2
  ethernets:
    enp0s1:
      dhcp4: false
      addresses:
        - 192.168.64.100/24
      routes:
        - to: default
          via: 192.168.64.1
      nameservers:
        addresses:
          - 8.8.8.8
          - 114.114.114.114
```

应用配置：
```bash
sudo netplan apply
```

**注意**：修改 IP 后需要重新配置 Tabby 的 Host。

---

## 5. ROS2 Humble 安装

### 5.1 设置软件源

```bash
# 安装依赖
sudo apt install -y software-properties-common
sudo add-apt-repository universe

# 添加 ROS2 GPG key
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg

# 添加 ROS2 软件源
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

# 更新
sudo apt update
```

### 5.2 安装 ROS2 Humble

```bash
# 安装桌面完整版（推荐，包含 turtlesim 等工具）
sudo apt install -y ros-humble-desktop

# 如果空间不足，可以只安装基础版
# sudo apt install -y ros-humble-ros-base
```

### 5.3 安装开发工具

```bash
sudo apt install -y \
  python3-colcon-common-extensions \
  python3-rosdep \
  python3-vcstool \
  python3-pip \
  build-essential
```

### 5.4 配置环境变量

```bash
# 永久生效（添加到 ~/.bashrc）
echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

### 5.5 初始化 rosdep

```bash
sudo rosdep init
rosdep update
```

**如果 rosdep update 超时**，使用国内镜像：

```bash
# 备份原配置
sudo cp /etc/ros/rosdep/sources.list.d/20-default.list /etc/ros/rosdep/sources.list.d/20-default.list.bak

# 使用清华镜像
sudo sed -i 's|https://raw.githubusercontent.com/ros/rosdistro/master|https://mirror.tuna.tsinghua.edu.cn/rosdistro|g' /etc/ros/rosdep/sources.list.d/20-default.list

# 重新更新
rosdep update
```

### 5.6 安装项目依赖包

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

### 5.7 验证 ROS2 安装（测试 X11 转发）

```bash
# 测试 turtlesim
ros2 run turtlesim turtlesim_node
```

如果 X11 配置正确，会在 macOS 上弹出 turtlesim 窗口！

如果窗口没有弹出：
1. 检查 macOS 是否安装了 XQuartz
2. 检查 Tabby 是否启用了 X11 forwarding
3. 尝试手动设置 DISPLAY：
   ```bash
   export DISPLAY=:0
   ros2 run turtlesim turtlesim_node
   ```

---

## 6. 项目代码拉取与构建

### 6.1 拉取代码

```bash
# 创建项目目录
mkdir -p ~/ROS2
cd ~/ROS2

# 克隆 work 分支（只包含 ros2_ws 代码）
git clone --branch work --depth 1 https://github.com/Ringdownn/ROS2.git

# 进入目录
cd ROS2

# 验证文件
ls -la
# 应该只看到 ros2_ws 目录
tree ros2_ws/src -L 3
```

### 6.2 构建项目

```bash
cd ~/ROS2/ros2_ws

# 清理（如果是重新构建）
rm -rf build/ install/ log/

# 构建
colcon build

# 加载环境
source install/setup.bash

# 验证包
ros2 pkg list | grep catch_turtle
ros2 interface show catch_turtle_interfaces/action/CatchTarget
```

### 6.3 配置快捷命令（可选）

由于 `ros2 run` 可能出现 `No executable found` 的问题，建议配置别名：

```bash
# 添加到 ~/.bashrc
cat >> ~/.bashrc << 'EOF'

# ROS2 workspace
source ~/ROS2/ros2_ws/install/setup.bash

# Catch Turtle aliases
alias spawn_manager='~/ROS2/ros2_ws/install/catch_turtle_bringup/bin/spawn_manager'
alias master_manager='~/ROS2/ros2_ws/install/catch_turtle_bringup/bin/master_manager'
alias catch_executor='~/ROS2/ros2_ws/install/catch_turtle_bringup/bin/catch_executor'
alias follower_manager='~/ROS2/ros2_ws/install/catch_turtle_bringup/bin/follower_manager'
EOF

source ~/.bashrc
```

---

## 7. 功能验证

按照 `catch_turtle_vm_verify_plan.md` 进行验证：

### 阶段 C：仿真 + 生成

**终端 1：**
```bash
ros2 run turtlesim turtlesim_node
```

**终端 2：**
```bash
~/ROS2/ros2_ws/install/catch_turtle_bringup/bin/spawn_manager
```

### 阶段 D：手动抓一只

**终端 1：**
```bash
ros2 run turtlesim turtlesim_node
```

**终端 2：**
```bash
~/ROS2/ros2_ws/install/catch_turtle_bringup/bin/spawn_manager
```

**终端 3：**
```bash
~/ROS2/ros2_ws/install/catch_turtle_bringup/bin/catch_executor
```

**终端 4：**
```bash
ros2 action send_goal /catch_target \
  catch_turtle_interfaces/action/CatchTarget \
  "{target_name: 'turtle2'}" --feedback
```

### 阶段 G：一键启动

```bash
ros2 launch catch_turtle_bringup catch_turtle.launch.py
```

---

## 8. 常见问题排查

### 问题 1：SSH 连接失败

**原因：** IP 地址错误、防火墙、SSH 服务未启动

**解决：**
```bash
# 在虚拟机中检查 IP
ip addr show

# 检查 SSH 服务
sudo systemctl status ssh
sudo systemctl start ssh

# 检查防火墙
sudo ufw status
sudo ufw allow ssh
```

### 问题 2：X11 转发不工作（turtlesim 窗口不弹出）

**原因：** macOS 未安装 XQuartz、Tabby 未启用 X11 forwarding

**解决：**
```bash
# 1. macOS 安装 XQuartz
brew install --cask xquartz
# 安装后重启 macOS

# 2. Tabby 中勾选 "Enable X11 forwarding"

# 3. 测试
export DISPLAY=:0
ros2 run turtlesim turtlesim_node
```

### 问题 3：ros2 run 报 No executable found

**原因：** ROS2 daemon 缓存问题

**解决：**
```bash
# 方法 1：重启 daemon
ros2 daemon stop
ros2 daemon start

# 方法 2：使用完整路径
~/ROS2/ros2_ws/install/catch_turtle_bringup/bin/spawn_manager
```

### 问题 4：rosdep update 超时

**原因：** 网络问题，无法访问 GitHub raw

**解决：**
```bash
# 使用国内镜像
sudo sed -i 's|https://raw.githubusercontent.com/ros/rosdistro/master|https://mirror.tuna.tsinghua.edu.cn/rosdistro|g' /etc/ros/rosdep/sources.list.d/20-default.list
rosdep update
```

### 问题 5：磁盘空间不足

**解决：**
```bash
# 查看空间使用
df -h
du -sh ~/* | sort -hr

# 清理
sudo apt clean
sudo apt autoremove -y
sudo rm -rf /var/log/*.gz
rm -rf ~/ROS2/ros2_ws/build ~/ROS2/ros2_ws/log
```

### 问题 6：catch_executor 抓到目标后崩溃

**现象：** `Failed to send result response (the client may have gone away)`

**解决：** 已修复，请拉取最新 work 分支代码重新构建。

---

## 附录：快速命令清单

```bash
# === 环境设置 ===
source /opt/ros/humble/setup.bash
source ~/ROS2/ros2_ws/install/setup.bash

# === 构建 ===
cd ~/ROS2/ros2_ws
colcon build

# === 运行节点 ===
ros2 run turtlesim turtlesim_node
~/ROS2/ros2_ws/install/catch_turtle_bringup/bin/spawn_manager
~/ROS2/ros2_ws/install/catch_turtle_bringup/bin/catch_executor
~/ROS2/ros2_ws/install/catch_turtle_bringup/bin/master_manager
~/ROS2/ros2_ws/install/catch_turtle_bringup/bin/follower_manager

# === 一键启动 ===
ros2 launch catch_turtle_bringup catch_turtle.launch.py

# === 查看状态 ===
ros2 node list
ros2 topic list
ros2 action list
ros2 topic echo /caught_chain
```

---

> 文档版本：2.0
> 最后更新：2025-05-08
> 适用项目：Catch Turtle All
> 主要变更：改为 UTM + SSH 方案，移除 VMware 相关内容
