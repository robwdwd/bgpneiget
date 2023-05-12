# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#
from typing import Type

from scrapli.driver.core import AsyncJunosDriver

from bgpneiget.device.base import BaseDevice


class JunOsDevice(BaseDevice):
    """Juniper JunOS devices."""

    def get_driver(self) -> Type[AsyncJunosDriver]:
        """Get scrapli driver for this device.

        Returns:
            Type[AsyncJunosDriver]: Scrapli Driver
        """
        return AsyncJunosDriver

    def get_ipv4_bgp_sum_cmd(self) -> str:
        """Get the BGP summary show command for this device.

        Returns:
            str: BGP summary show command
        """
        return "show bgp sum"
