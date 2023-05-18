# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#
import ipaddress
import logging
import pprint
from typing import Type

import xmltodict
from scrapli.driver.core import AsyncJunosDriver

from bgpneiget.device.base import BaseDevice
from bgpneiget.runcmds import get_output

pp = pprint.PrettyPrinter(indent=2, width=120)

logger = logging.getLogger()


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
        return "show bgp neighbor | display xml"

    async def process_bgp_neighbours(self, result: list, table: str, prog_args: dict) -> list:
        """Process the BGP Neigbour output from devices through textFSM.

        Args:
            result (list): Parsed output from network device
            prog_args (dict): Program arguments, asignore etc.

        Returns:
            dict: BGP Neighbours
        """
        try:
            data = xmltodict.parse(result)
        except Exception as err:
            raise err

        pp.pprint(data)

        if "rpc-reply" not in data:
            return []

        if "bgp-information" not in data["rpc-reply"]:
            return []

        if "bgp-peer" not in data["rpc-reply"]["bgp-information"]:
            return []

        for bgp_peer in data["rpc-reply"]["bgp-information"]["bgp-peer"]:
            remote_ip = bgp_peer["peer-address"]
            if "+" in remote_ip:
                remote_ip = remote_ip[0 : remote_ip.find("+")]
            remote_ip = ipaddress.ip_address(remote_ip)

            results[str(remote_ip)] = {}

        return results

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

        response["all"] = response["all"][: response["all"].rfind("\n")]

        pp.pprint(response)

        result = self.parse_bgp_neighbours(response["all"])

        return result
