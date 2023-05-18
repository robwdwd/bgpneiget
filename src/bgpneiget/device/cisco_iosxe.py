# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#
import asyncio
import ipaddress
import os
import pprint
import sys
from typing import Type

from scrapli.driver.core import AsyncIOSXEDriver
from textfsm import TextFSM

from bgpneiget.device.base import BaseDevice
from bgpneiget.runcmds import get_output

pp = pprint.PrettyPrinter(indent=2, width=120)


class CiscoIOSDevice(BaseDevice):
    """Cisco IOS and IOS-XE devices."""

    def get_driver(self) -> Type[AsyncIOSXEDriver]:
        """Get scrapli driver for this device.

        Returns:
            Type[AsyncIOSXEDriver]: Scrapli Driver
        """
        return AsyncIOSXEDriver

    def get_bgp_cmd_global(self, table: str) -> str:
        """Get the BGP summary show command for this device.

        Returns:
            str: BGP summary show command
        """
        if table == "ipv4":
            return "show ip bgp summary"
        elif table == "ipv6":
            return "show bgp ipv6 unicast summary"
        elif table == "vpnv4":
            return "show bgp vpnv4 unicast all neighbors | include BGP neighbor is | Prefixes | BGP state | For address"
        elif table == "vpnv6":
            return "show bgp vpnv6 unicast all neighbors | include BGP neighbor is | Prefixes | BGP state | For address"
        else:
            raise ValueError("Unknown routing table.")

    async def process_bgp_neighbours(self, result: list, table: str, prog_args: dict) -> list:
        """Process the BGP Neigbour output from devices through textFSM.

        Args:
            result (list): Parsed output from network device
            table (str): Forwarding table (ipv4, ipv6, vpnv4 or vpnv6)
            prog_args (dict): Program arguments, asignore etc.

        Returns:
            list: BGP Neighbours
        """

        #   { 'BGP_INSTANCE': 'default',
        #     'BGP_NEIGH': '100.65.5.175',
        #     'NEIGH_AS': '65505',
        #     'STATE_PFXRCD': '3',
        #     'VRF': 'VRF-IPC103293-1-00005'},

        pp.pprint(table)

        results = []
        for neighbour in result:
            pp.pprint(neighbour)
            addr = ipaddress.ip_address(neighbour["BGP_NEIGH"])

            if prog_args["verbose"] >= 1:
                print(f"DEBUG: Found neighbour {neighbour}", file=sys.stderr)

            ipversion = addr.version
            as_number = int(neighbour["NEIGH_AS"])

            if prog_args["except_as"] and (as_number not in prog_args["except_as"]):
                continue

            if prog_args["ignore_as"] and as_number in prog_args["ignore_as"]:
                continue

            is_up = False
            pfxrcd = -1
            state = "Established"
            if neighbour["STATE_PFXRCD"].isdigit():
                is_up = True
                pfxrcd = neighbour["STATE_PFXRCD"]
            else:
                state = neighbour["STATE_PFXRCD"]

            routing_instance = "default"
            if "VRF" in neighbour and neighbour["VRF"]:
                routing_instance = neighbour["VRF"]

            protocol_instance = "default"
            if "BGP_INSTANCE" in neighbour and neighbour["BGP_INSTANCE"]:
                protocol_instance = neighbour["BGP_INSTANCE"]

            results.append(
                {
                    "remote_ip": str(addr),
                    "remote_asn": as_number,
                    "address_family": table,
                    "ip_version": ipversion,
                    "is_up": is_up,
                    "pfxrcd": pfxrcd,
                    "state": state,
                    "routing_instance": routing_instance,
                    "protocol_instance": protocol_instance,
                }
            )

        return results

    def parse_bgp_neighbours(self, output: str, filename: str) -> list:
        """Process the BGP Neigbour output from devices through textFSM.

        Args:
            output (str): Output from network device

            filename (str): Template filename

        Returns:
            dict: BGP Neighbours
        """
        try:
            template_file = os.path.join(os.path.dirname(__file__), f"../textfsm/{filename}")
            with open(template_file) as template:
                fsm = TextFSM(template)

        except OSError as err:
            raise OSError(f"ERROR: Unable to open textfsm template: {err}") from err

        return fsm.ParseTextToDicts(output)

    async def get_neighbours(self, prog_args: dict) -> list:
        """Get BGP neighbours from device.

        Args:
            prog_args (dict): Program arguments

        Returns:
            list: Found BGP neighbours
        """
        commands = {}
        reverse_commands = {}

        for table in prog_args["table"]:
            cmd = self.get_bgp_cmd_global(table)
            commands[table] = cmd
            reverse_commands[cmd] = table

        pp.pprint(commands)
        response = await get_output(self, commands, prog_args["username"], prog_args["password"])

        loop = asyncio.get_running_loop()

        result = []

        template_file = f"{self.platform}_show_bgp.textfsm"

        for resp in response:
            table = reverse_commands[resp.channel_input]
            if table in ("vpnv4", "vpnv6"):
                template_file = "cisco_iosxe_show_bgp_vrf.textfsm"
            else:
                template_file = "cisco_iosxe_show_bgp.textfsm"

            parsed_result = await loop.run_in_executor(None, self.parse_bgp_neighbours, resp.result, template_file)
            pp.pprint(parsed_result)

            result = result + await self.process_bgp_neighbours(parsed_result, table, prog_args)

        return result
