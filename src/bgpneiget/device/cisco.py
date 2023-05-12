# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#
from typing import Type

from scrapli.driver.core import AsyncIOSXEDriver, AsyncIOSXRDriver, AsyncNXOSDriver

from bgpneiget.device.base import BaseDevice


class CiscoIOSDevice(BaseDevice):
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


class CiscoIOSXRDevice(BaseDevice):
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


class CiscoNXOSDevice(BaseDevice):
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
