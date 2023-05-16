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

    def process_bgp_neighbours(self, output: str, prog_args: dict) -> dict:
        """Process the BGP Neigbour output from devices through textFSM.

        Args:
            platform (str): Device platform
            output (str): Output from network device
            prog_args (dict): Program arguments, asignore etc.

        Returns:
            dict: BGP Neighbours
        """
        try:
            template_file = os.path.join(os.path.dirname(__file__), "../textfsm/cisco_iosxr_show_bgp.textfsm")
            with open(template_file) as template:
                fsm = TextFSM(template)

        except OSError as err:
            raise OSError(f"ERROR: Unable to open textfsm template: {err}") from err

        pp.pprint(output)

        result = fsm.ParseText(output)

        pp.pprint(result)

        results = {}
        for neighbour in result:
            addr = ipaddress.ip_address(neighbour[3])

            if prog_args["verbose"] >= 1:
                print(f"DEBUG: Found neighbour {neighbour}", file=sys.stderr)

            ipversion = addr.version
            as_number = int(neighbour[4])

            if prog_args["except_as"] and (as_number not in prog_args["except_as"]):
                continue

            if prog_args["ignore_as"] and as_number in prog_args["ignore_as"]:
                continue

            is_up = False
            if neighbour[6].isdigit():
                is_up = True

            routing_instance = "global"
            if neighbour[2]:
                routing_instance = neighbour[2]

            results[str(addr)] = {
                "remote_asn": as_number,
                "local_asn": int(neighbour[1]),
                "ip_version": ipversion,
                "is_up": is_up,
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
                None, self.process_bgp_neighbours, self.platform, response[addrf], prog_args
            )
            if len(parsed_result) > 0:
                result[addrf] = parsed_result

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
                None, self.process_bgp_neighbours, self.platform, response[addrf], prog_args
            )
            if len(parsed_result) > 0:
                result[addrf] = parsed_result

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
