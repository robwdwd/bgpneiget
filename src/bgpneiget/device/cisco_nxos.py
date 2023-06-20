# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#
import asyncio
import ipaddress
import logging
import os
import pprint
from typing import Type

from scrapli.driver.core import AsyncNXOSDriver
from scrapli.exceptions import ScrapliException
from textfsm import TextFSM

from bgpneiget.device.base import BaseDevice
from bgpneiget.runcmds import get_output

pp = pprint.PrettyPrinter(indent=2, width=120)

logger = logging.getLogger()


class CiscoNXOSDevice(BaseDevice):
    """Cisco NX-OS devices."""

    def get_driver(self) -> Type[AsyncNXOSDriver]:
        """Get scrapli driver for this device.

        Returns:
            Type[AsyncNXOSDriver]: Scrapli Driver
        """
        return AsyncNXOSDriver

    def get_bgp_cmd_global(self, table: str) -> str:
        """Get the BGP summary show command for this device.

        Returns:
            str: BGP summary show command
        """
        return "show ip bgp summary"
