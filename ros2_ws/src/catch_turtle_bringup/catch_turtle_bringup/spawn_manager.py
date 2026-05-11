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
