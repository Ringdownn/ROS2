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
        self.declare_parameter('follow_distance', 0.5)
        self.declare_parameter('linear_speed', 2.0)
        self.declare_parameter('angular_speed', 3.0)
        self.declare_parameter('max_angular_speed', 4.0)
        self.declare_parameter('angle_tolerance', 0.1)
        self.declare_parameter('control_rate_hz', 20.0)
        self.declare_parameter('linear_kp', 2.0)
        self.declare_parameter('angular_kp', 3.0)

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

            target_angle = utils.angle_to(
                f_pose.x, f_pose.y, l_pose.x, l_pose.y,
            )
            angle_err = utils.normalize_angle(target_angle - f_pose.theta)

            if dist < follow_distance * 0.5:
                if abs(angle_err) < angle_tolerance:
                    twist.linear.x = -linear_speed * 0.3
                else:
                    twist.angular.z = utils.clamp(
                        angular_kp * angle_err,
                        -max_angular_speed, max_angular_speed,
                    )
                pub.publish(twist)
                continue

            if abs(angle_err) > angle_tolerance:
                twist.angular.z = utils.clamp(
                    angular_kp * angle_err,
                    -max_angular_speed, max_angular_speed,
                )
            
            if dist > follow_distance:
                speed = linear_kp * (dist - follow_distance)
                twist.linear.x = utils.clamp(speed, 0.0, linear_speed)
            
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
