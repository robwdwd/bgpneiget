# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#
import json
import pprint
from json import JSONDecodeError
from typing import Type

from scrapli.driver.core import AsyncJunosDriver

from bgpneiget.device.base import BaseDevice
from bgpneiget.runcmds import get_output

pp = pprint.PrettyPrinter(indent=2, width=120)


class JunOsDevice(BaseDevice):
    """Juniper JunOS devices."""

    def get_driver(self) -> Type[AsyncJunosDriver]:
        """Get scrapli driver for this device.

        Returns:
            Type[AsyncJunosDriver]: Scrapli Driver
        """
        return AsyncJunosDriver

    def get_bgp_cmd_global(self, address_family: str = "ipv4") -> str:
        """Get the BGP summary show command for this device.

        Returns:
            str: BGP summary show command
        """
        return "show bgp sum | display json"

    async def process_bgp_neighbours(self, result: list, prog_args: dict) -> dict:
        """Process the BGP Neigbour output from devices through textFSM.

        Args:
            result (list): Parsed output from network device
            prog_args (dict): Program arguments, asignore etc.

        Returns:
            dict: BGP Neighbours
        """
        pp.pprint(result)

    async def get_neighbours(self, prog_args: dict) -> dict:
        """Get BGP neighbours from device.

        Args:
            prog_args (dict): Program arguments

        Returns:
            dict: Found BGP neighbours
        """
        commands = {}

        commands["all"] = self.get_bgp_cmd_global()

        pp.pprint(commands)
        response = await get_output(self, commands, prog_args["username"], prog_args["password"])

        pp.pprint(response)
        try:
            result = json.loads(response["all"])
        except JSONDecodeError as err:
            raise err

        return result
