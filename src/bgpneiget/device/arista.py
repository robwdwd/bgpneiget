# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#
from typing import Type

from scrapli.driver.core import AsyncEOSDriver

from bgpneiget.device.base import BaseDevice


class EOSDevice(BaseDevice):
    """Arista EOS devices."""

    def get_driver(self) -> Type[AsyncEOSDriver]:
        """Get scrapli driver for this device.

        Returns:
            Type[AsyncEOSDriver]: Scrapli Driver
        """
        return AsyncEOSDriver

    def get_bgp_cmd_global(self, address_family: str = "ipv4") -> str:
        """Get the BGP summary show command for this device.

        Returns:
            str: BGP summary show command
        """
        return "show bgp sum"
