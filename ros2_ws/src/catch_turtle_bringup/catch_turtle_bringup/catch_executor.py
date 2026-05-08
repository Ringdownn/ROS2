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
                try:
                    goal_handle.publish_feedback(feedback)
                except Exception as e:
                    self.get_logger().warn(f'Failed to publish feedback: {e}')

                if dist < catch_distance:
                    self._publish_zero()
                    result.success = True
                    result.caught_name = target_name
                    try:
                        goal_handle.succeed()
                    except Exception as e:
                        self.get_logger().warn(f'Failed to send success result: {e}')
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
            try:
                self.destroy_subscription(target_sub)
            except Exception:
                pass
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
