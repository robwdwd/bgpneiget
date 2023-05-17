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

from scrapli.driver.core import AsyncIOSXEDriver, AsyncIOSXRDriver, AsyncNXOSDriver
from textfsm import TextFSM

from bgpneiget.device.base import BaseDevice
from bgpneiget.runcmds import get_output

pp = pprint.PrettyPrinter(indent=2, width=120)


class CiscoDevice(BaseDevice):
    """Base class for all Cisco Devices."""

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

    def process_bgp_neighbours(self, result: list, prog_args: dict) -> dict:
        """Process the BGP Neigbour output from devices through textFSM.

        Args:
            result (list): Parsed output from network device
            prog_args (dict): Program arguments, asignore etc.

        Returns:
            dict: BGP Neighbours
        """

        # { 'BGP_NEIGH': '80.169.21.153',
        #     'LOCAL_AS': '8220',
        #     'NEIGH_AS': '15404',
        #     'ROUTER_ID': '212.74.94.143',
        #     'STATE_PFXRCD': '1',
        #     'UP_DOWN': '2w5d',
        #     'VRF': 'default'},

        results = {}
        for neighbour in result:
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
            state = 'Established'
            if neighbour["STATE_PFXRCD"].isdigit():
                is_up = True
                pfxrcd = neighbour["STATE_PFXRCD"]
            else:
                state = neighbour["STATE_PFXRCD"]

            routing_instance = "global"
            if 'VRF' in neighbour and neighbour["VRF"]:
                routing_instance = neighbour["VRF"]

            results[str(addr)] = {
                "remote_asn": as_number,
                "local_asn": int(neighbour["LOCAL_AS"]),
                "ip_version": ipversion,
                "is_up": is_up,
                "pfxrcd": pfxrcd,
                'state': state,
                "up_down_time": neighbour["UP_DOWN"],
                "routing_instance": routing_instance,
            }

        return results


class CiscoIOSXRDevice(CiscoDevice):
    """Cisco IOS-XR devices."""

    def get_driver(self) -> Type[AsyncIOSXRDriver]:
        """Get scrapli driver for this device.

        Returns:
            Type[AsyncIOSXRDriver]: Scrapli Driver
        """
        return AsyncIOSXRDriver

    async def get_neighbours(self, prog_args: dict) -> dict:
        """Get BGP neighbours from device.

        Args:
            prog_args (dict): Program arguments

        Returns:
            dict: Found BGP neighbours
        """
        commands = {}

        if not prog_args["no_ipv4"]:
            commands["ipv4"] = self.get_bgp_cmd_global()
            if prog_args["with_vrfs"]:
                commands["ipv4_vrfs"] = self.get_bgp_cmd_vrfs("ipv4")

        if not prog_args["no_ipv6"]:
            commands["ipv6"] = self.get_bgp_cmd_global("ipv6")
            if prog_args["with_vrfs"]:
                commands["ipv6_vrfs"] = self.get_bgp_cmd_vrfs("ipv6")

        if prog_args["vpnv4"]:
            commands["vpnv4"] = self.get_bgp_cmd_global("vpnv4")

        if prog_args["vpnv6"]:
            commands["vpnv6"] = self.get_bgp_cmd_global("vpnv6")

        pp.pprint(commands)
        response = await get_output(self, commands, prog_args["username"], prog_args["password"])

        result = {}

        loop = asyncio.get_running_loop()

        for addrf in response:
            parsed_result = await loop.run_in_executor(
                None, self.parse_bgp_neighbours, response[addrf], "cisco_iosxr_show_bgp.textfsm"
            )
            pp.pprint(parsed_result)
            if len(parsed_result) > 0:
                result[addrf] = self.process_bgp_neighbours(parsed_result, prog_args)

        return result

    def get_bgp_cmd_global(self, address_family: str = "ipv4") -> str:
        """Get the BGP summary show command for this device.

        Returns:
            str: BGP summary show command
        """
        return f"show bgp instance all {address_family} unicast summary"

    def get_bgp_cmd_vrfs(self, address_family: str = "ipv4") -> str:
        """Get the BGP summary show command for this device.

        Returns:
            str: BGP summary show command
        """
        return f"show bgp vrf all {address_family} unicast summary"


class CiscoIOSDevice(CiscoDevice):
    """Cisco IOS and IOS-XE devices."""

    def get_driver(self) -> Type[AsyncIOSXEDriver]:
        """Get scrapli driver for this device.

        Returns:
            Type[AsyncIOSXEDriver]: Scrapli Driver
        """
        return AsyncIOSXEDriver

    async def get_neighbours(self, prog_args: dict) -> dict:
        """Get BGP neighbours from device.

        Args:
            prog_args (dict): Program arguments

        Returns:
            dict: Found BGP neighbours
        """
        commands = {}

        if not prog_args["no_ipv4"]:
            commands["ipv4"] = self.get_bgp_cmd_global()

        if not prog_args["no_ipv6"]:
            commands["ipv6"] = self.get_bgp_cmd_global("ipv6")

        if prog_args["vpnv4"]:
            commands["vpnv4"] = self.get_bgp_cmd_global("vpnv4")

        if prog_args["vpnv6"]:
            commands["vpnv6"] = self.get_bgp_cmd_global("vpnv6")

        pp.pprint(commands)
        response = await get_output(self, commands, prog_args["username"], prog_args["password"])

        result = {}

        loop = asyncio.get_running_loop()

        for addrf in response:
            parsed_result = await loop.run_in_executor(
                None, self.parse_bgp_neighbours, response[addrf], "cisco_iosxe_show_bgp.textfsm"
            )
            pp.pprint(parsed_result)
            if len(parsed_result) > 0:
                result[addrf] = self.process_bgp_neighbours(parsed_result, prog_args)

        return result

    def get_bgp_cmd_global(self, address_family: str = "ipv4") -> str:
        """Get the BGP summary show command for this device.

        Returns:
            str: BGP summary show command
        """
        if address_family == "ipv4":
            return "show ip bgp summary"
        elif address_family == "ipv6":
            return "show bgp ipv6 unicast summary"
        elif address_family == "vpnv4":
            return "show ip bgp vpnv4 all summary"
        elif address_family == "vpnv6":
            return "show ip bgp vpnv6 unicast all summary"

        return ""


class CiscoNXOSDevice(CiscoDevice):
    """Cisco NX-OS devices."""

    def get_driver(self) -> Type[AsyncNXOSDriver]:
        """Get scrapli driver for this device.

        Returns:
            Type[AsyncNXOSDriver]: Scrapli Driver
        """
        return AsyncNXOSDriver

    def get_bgp_cmd_global(self, address_family: str = "ipv4") -> str:
        """Get the BGP summary show command for this device.

        Returns:
            str: BGP summary show command
        """
        return "show ip bgp summary"

    def get_bgp_cmd_vrfs(self, address_family: str = "ipv4") -> str:
        """Get the BGP summary show command for this device.

        Returns:
            str: BGP summary show command
        """
        return "show bgp ipv6 unicast summary"
