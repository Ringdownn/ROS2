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
