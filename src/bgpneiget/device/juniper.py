# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#
import ipaddress
import logging
import pprint
from typing import Tuple, Type

import xmltodict
from scrapli.driver.core import AsyncJunosDriver

from bgpneiget.device.base import BaseDevice
from bgpneiget.runcmds import get_output

pp = pprint.PrettyPrinter(indent=2, width=120)

logger = logging.getLogger()


class JunOsDevice(BaseDevice):
    """Juniper JunOS devices."""

    AF_MAP = {"inet": "ipv4", "inet6": "ipv6"}

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

    async def process_bgp_neighbours(self, result: str, prog_args: dict) -> list:
        """Process the BGP Neigbour output from devices through textFSM.

        Args:
            result (str): XML string from JunOS device
            prog_args (dict): Program arguments, asignore etc.

        Returns:
            dict: BGP Neighbours
        """
        try:
            data = xmltodict.parse(result)
        except Exception as err:
            raise err

        if "rpc-reply" not in data:
            return []

        if "bgp-information" not in data["rpc-reply"]:
            return []

        if "bgp-peer" not in data["rpc-reply"]["bgp-information"]:
            return []

        results = []

        for bgp_peer in data["rpc-reply"]["bgp-information"]["bgp-peer"]:
            new_neighbour = {
                "remote_ip": "",
                "remote_asn": -1,
                "address_family": "",
                "ip_version": -1,
                "is_up": False,
                "pfxrcd": -1,
                "state": "",
                "routing_instance": "default",
                "protocol_instance": "default",
            }
            pp.pprint(bgp_peer)

            remote_ip: str = bgp_peer["peer-address"]
            if "+" in remote_ip:
                remote_ip = remote_ip[0 : remote_ip.find("+")]
            addr = ipaddress.ip_address(remote_ip)

            new_neighbour["remote_ip"] = str(addr)

            as_number = int(bgp_peer["peer-as"])

            if prog_args["except_as"] and (as_number not in prog_args["except_as"]):
                logger.debug(
                    "DEBUG: Ignoring neighbour '%s', '%s' not in except AS list.",
                    str(addr),
                    as_number,
                )
                continue

            if prog_args["ignore_as"] and as_number in prog_args["ignore_as"]:
                logger.debug(
                    "DEBUG: Ignoring neighbour '%s', '%s' in ignored AS list.",
                    str(addr),
                    as_number,
                )
                continue

            new_neighbour["as_number"] = as_number

            if bgp_peer["peer-state"] == "Established":
                new_neighbour["is_up"] = True
                new_neighbour["state"] = "Established"
            else:
                new_neighbour["state"] = bgp_peer["peer-state"]

            routing_instance = "default" if bgp_peer["peer-fwd-rti"] == "master" else bgp_peer["peer-fwd-rti"]
            address_family = ""
            # address_family = bgp_peer["nlri-type-peer"]

            # BGP RIB must exist
            if "bgp-rib" in bgp_peer:
                if isinstance(bgp_peer["bgp-rib"], dict):
                    (address_family, routing_instance) = await self.parse_bgp_rib(bgp_peer["bgp-rib"])
                    if not address_family or not routing_instance:
                        logger.error("Neighbour '%s' has unparsable address family.", str(addr))
                    else:
                        new_neighbour["address_family"] = address_family
                        new_neighbour["routing_instance"] = routing_instance
                        results.append(new_neighbour)

                elif isinstance(bgp_peer["bgp-rib"], list):
                    for table in bgp_peer["bgp-rib"]:
                        (address_family, routing_instance) = await self.parse_bgp_rib(table)
                        if not address_family or not routing_instance:
                            logger.error("Neighbour '%s' has unparsable address family.", str(addr))
                        else:
                            new_nei = new_neighbour.copy()
                            new_nei["address_family"] = address_family
                            new_nei["routing_instance"] = routing_instance
                            results.append(new_nei)

        return results

    async def parse_bgp_rib(
        self,
        rib,
    ) -> Tuple[str, str]:
        family = rib["name"].rsplit(".")
        pp.pprint(family)
        if len(family) == 2:
            address_family = family[0]
            routing_instance = "default"
        elif len(family) == 3:
            address_family = family[1]
            routing_instance = family[0]
        else:
            return ()

        try:
            address_family = self.AF_MAP[address_family]
        except KeyError:
            return ()

        pp.pprint([address_family, routing_instance])

        return (address_family, routing_instance)

    async def get_neighbours(self, prog_args: dict) -> dict:
        """Get BGP neighbours from device.

        Args:
            prog_args (dict): Program arguments

        Returns:
            dict: Found BGP neighbours
        """
        commands = {}

        commands["all"] = self.get_bgp_cmd_global()

        pp.pprint(list(commands.values()))
        response = await get_output(self, commands, prog_args["username"], prog_args["password"])

        result = []

        for resp in response:
            stripped_response = resp.result[: resp.result.rfind("\n")]
            result = result + await self.process_bgp_neighbours(stripped_response, prog_args)

        return result
