# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#
import pprint
from typing import Type

import textfsm
from scrapli.driver.core import AsyncIOSXEDriver, AsyncIOSXRDriver, AsyncNXOSDriver

from bgpneiget.device.base import BaseDevice

pp = pprint.PrettyPrinter(indent=2, width=120)

class CiscoDevice(BaseDevice):
    """Base class for all Cisco Devices"""

    async def process_bgp_neighbours(self, output: str):
        with open('textfsm/cisco_iosxe_show_ip_bgp_sum.textfsm') as template:
            fsm = textfsm.TextFSM(template)
            result = fsm.ParseText(output)
            pp.pprint(result)


class CiscoIOSDevice(CiscoDevice):
    """Cisco IOS and IOS-XE devices."""

    def get_driver(self) -> Type[AsyncIOSXEDriver]:
        """Get scrapli driver for this device.

        Returns:
            Type[AsyncIOSXEDriver]: Scrapli Driver
        """
        return AsyncIOSXEDriver

    def get_ipv4_bgp_sum_cmd(self) -> str:
        """Get the BGP summary show command for this device.

        Returns:
            str: BGP summary show command
        """
        return "show ip bgp sum"


class CiscoIOSXRDevice(CiscoDevice):
    """Cisco IOS-XR devices."""

    def get_driver(self) -> Type[AsyncIOSXRDriver]:
        """Get scrapli driver for this device.

        Returns:
            Type[AsyncIOSXRDriver]: Scrapli Driver
        """
        return AsyncIOSXRDriver

    def get_ipv4_bgp_sum_cmd(self) -> str:
        """Get the BGP summary show command for this device.

        Returns:
            str: BGP summary show command
        """
        return "show bgp sum"


class CiscoNXOSDevice(CiscoDevice):
    """Cisco NX-OS devices."""

    def get_driver(self) -> Type[AsyncNXOSDriver]:
        """Get scrapli driver for this device.

        Returns:
            Type[AsyncNXOSDriver]: Scrapli Driver
        """
        return AsyncNXOSDriver

    def get_ipv4_bgp_sum_cmd(self) -> str:
        """Get the BGP summary show command for this device.

        Returns:
            str: BGP summary show command
        """
        return "show bgp sum"
