# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#
"""Base Class for all device types."""

from typing import Dict, Type

from scrapli.driver import AsyncNetworkDriver


class BaseDevice:
    """Base Class for all device types."""

    PROTOCOL_TRANSPORT_MAP = {
        "TELNET": "telnet",
        "SSH": "asyncssh",
    }

    def __init__(self, device: dict) -> None:
        """Init.

        Args:
            device (dict): Dictionary of device data.
        """
        self.os = device["os"]
        self.hostname = device["hostname"]
        self.transport = self.PROTOCOL_TRANSPORT_MAP[device["protocol"]]

    def setup_device_args(self, username: str, password: str) -> Dict:
        """Set up some default device arguments.

        Args:
            username (str): Username
            password (str): Password

        Returns:
            dict: Host args
        """

        return {
            "host": self.hostname,
            "auth_strict_key": False,
            "transport": self.transport,
            "auth_username": username,
            "auth_password": password,
        }

    def get_driver(self) -> Type[AsyncNetworkDriver]:
        """Get scrapli driver for this device.

        Returns:
            Type[AsyncNetworkDriver]: Scrapli Driver
        """
        return AsyncNetworkDriver

    def bgp_sum_cmd(self) -> str:
        """Get the BGP Summary show command for this device.

        Returns:
            str: BGP summary show command
        """
        return ""
