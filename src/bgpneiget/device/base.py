# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#
"""Base Class for all device types."""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Type

from scrapli.driver import AsyncNetworkDriver

logger = logging.getLogger()


class BaseDevice(ABC):
    """Base Class for all device types."""

    PROTOCOL_TRANSPORT_MAP = {
        "TELNET": "asynctelnet",
        "SSH": "asyncssh",
    }

    PLATFORM_MAP = {
        "IOS": "cisco_iosxe",
        "IOS-XE": "cisco_iosxe",
        "IOS-XR": "cisco_iosxr",
        "JunOS": "juniper_junos",
        "EOS": "arista_eos",
        "NX_OS": "cisco_nxos",
    }

    def __init__(self, device: dict) -> None:
        """Init.

        Args:
            device (dict): Dictionary of device data.
        """
        self.platform = self.PLATFORM_MAP[device["os"]]
        self.os = device["os"]
        self.hostname = device["hostname"]
        self.transport = self.PROTOCOL_TRANSPORT_MAP[device["protocol"]]

    def get_driver_options(self, username: str, password: str) -> Dict:
        """Set up some default device arguments.

        Args:
            username (str): Username
            password (str): Password

        Returns:
            dict: Host args
        """
        driver_options = {
            "host": self.hostname,
            "transport": self.transport,
            "auth_username": username,
            "auth_password": password,
        }

        # Add in some extra Kex and Cyphers for legacy devices
        #
        if self.transport == "asyncssh":
            driver_options["transport_options"] = {
                "asyncssh": {
                    "kex_algs": "+diffie-hellman-group1-sha1,diffie-hellman-group-exchange-sha1",
                    "encryption_algs": "+3des-cbc",
                }
            }
            driver_options["auth_strict_key"] = False

        return driver_options

    def log_ignored_neighbour(self, hostname: str, remote_ip: str, reason: str):
        logger.debug("[%s] Ignoring neighbour '%s': %s", hostname, remote_ip, reason)

    def is_private_asn(self, as_number) -> bool:
        return not (1 <= as_number <= 23455 or 23457 <= as_number <= 64495 or 131072 <= as_number <= 4199999999)

    def validate_asn(self, prog_args: dict, remote_ip: str, as_number: int) -> bool:
        if prog_args["ignore_private_asn"] and self.is_private_asn(as_number):
            self.log_ignored_neighbour(self.hostname, remote_ip, f"AS'{as_number}' is reserved or private")
            return False

        if prog_args["except_as"] and (as_number not in prog_args["except_as"]):
            self.log_ignored_neighbour(self.hostname, remote_ip, f"'AS{as_number}' not in except AS list")
            return False

        if prog_args["ignore_as"] and as_number in prog_args["ignore_as"]:
            self.log_ignored_neighbour(self.hostname, remote_ip, f"'AS{as_number}' is in ignored AS list")
            return False
        
        return True

    @abstractmethod
    def get_driver(self) -> Type[AsyncNetworkDriver]:
        """Get scrapli driver for this device.

        Returns:
            Type[AsyncNetworkDriver]: Scrapli Driver
        """

    @abstractmethod
    def get_bgp_cmd_global(self, table: str) -> str:
        """Get the BGP summary show command for this device.

        Returns:
            str: BGP summary show command
        """

    @abstractmethod
    async def get_neighbours(self, prog_args: dict) -> list:
        """Get BGP neighbours from device.

        Args:
            prog_args (dict): Program arguments

        Returns:
            list: Found BGP neighbours
        """
