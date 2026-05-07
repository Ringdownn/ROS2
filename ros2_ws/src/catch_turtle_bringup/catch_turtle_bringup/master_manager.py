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
            self._goal_in_flight = False
            self._current_target = None
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
