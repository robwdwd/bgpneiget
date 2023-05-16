# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#
import asyncio
import ipaddress
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

    async def process_bgp_neighbours(self, platform: str, output: str, prog_args: dict) -> dict:
        """Process the BGP Neigbour output from devices through textFSM.

        Args:
            platform (str): Device platform
            output (str): Output from network device
            prog_args (dict): Program arguments, asignore etc.

        Returns:
            dict: BGP Neighbours
        """
        fsm: TextFSM = prog_args["fsm"][platform]

        pp.pprint(output)

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, fsm.ParseText, output)

        pp.pprint(result)

        return result

        results = {}
        for neighbour in result:
            addr = ipaddress.ip_address(neighbour[3])

            # If this is a private IP address then continue
            # unless the rfc1918 argument was given
            #
            if (not prog_args["rfc1918"]) and addr.is_private:
                if prog_args["verbose"] >= 2:
                    print(f"DEBUG: Skipping neighbour {neighbour} with a " "private IP.", file=sys.stderr)
                continue

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


class CiscoIOSDevice(CiscoDevice):
    """Cisco IOS and IOS-XE devices."""

    def get_driver(self) -> Type[AsyncIOSXEDriver]:
        """Get scrapli driver for this device.

        Returns:
            Type[AsyncIOSXEDriver]: Scrapli Driver
        """
        return AsyncIOSXEDriver

    def get_bgp_cmd(self) -> list:
        """Get the BGP summary show command for this device.

        Returns:
            str: BGP summary show command
        """
        return ["show ip bgp sum", "show bgp ipv6 unicast summary"]


class CiscoIOSXRDevice(CiscoDevice):
    """Cisco IOS-XR devices."""

    def get_driver(self) -> Type[AsyncIOSXRDriver]:
        """Get scrapli driver for this device.

        Returns:
            Type[AsyncIOSXRDriver]: Scrapli Driver
        """
        return AsyncIOSXRDriver

    # prog_args = {
    #     "username": cfg["username"],
    #     "password": cfg["password"],
    #     "except_as": cli_args["asexcept"],
    #     "verbose": cli_args["verbose"],
    #     "ignore_as": cli_args["asignore"],
    #     "vpnv4": cli_args["vpnv4"],
    #     "vpnv6": cli_args["vpnv6"],
    #     "exclude_ipv4": cli_args["exclude-ipv4"],
    #     "exclude_ipv6": cli_args["exclude-ipv6"],
    #     "fsm": fsm,
    # }

    async def get_neighbours(self, prog_args: dict):

        commands = {}

        if not prog_args["no_ipv4"]:
            commands['ipv4'] = self.get_bgp_cmd_global()
            if prog_args["with_vrfs"]:
              commands['vpnv4_vrfs'] = self.get_bgp_cmd_vrfs('ipv4')


        if not prog_args["no_ipv6"]:
            commands['ipv6'] = self.get_bgp_cmd_global('ipv6')
            if prog_args["with_vrfs"]:
              commands['vpnv6_vrfs'] = self.get_bgp_cmd_vrfs('ipv6')


        if prog_args["vpnv4"]:
            commands['vpnv4'] = self.get_bgp_cmd_global('vpnv4')

        if prog_args["vpnv6"]:
            commands['vpnv6'] = self.get_bgp_cmd_global('vpnv6')
 
        pp.pprint(commands)
        response = await get_output(self, commands, prog_args["username"], prog_args["password"])

        for addrf in response:
            pp.pprint(addrf)
            result = await self.process_bgp_neighbours(self.platform, response[addrf], prog_args)

        return response


    def get_bgp_cmd_global(self, address_family: str = 'ipv4') -> str:
        """Get the BGP summary show command for this device.

        Returns:
            str: BGP summary show command
        """
        return f"show bgp instance all {address_family} unicast summary"

    def get_bgp_cmd_vrfs(self, address_family: str = 'ipv4') -> str:
        """Get the BGP summary show command for this device.

        Returns:
            str: BGP summary show command
        """
        return f"show bgp vrf all {address_family} unicast summary"



class CiscoNXOSDevice(CiscoDevice):
    """Cisco NX-OS devices."""

    def get_driver(self) -> Type[AsyncNXOSDriver]:
        """Get scrapli driver for this device.

        Returns:
            Type[AsyncNXOSDriver]: Scrapli Driver
        """
        return AsyncNXOSDriver

    def get_bgp_cmd(self) -> list:
        """Get the BGP summary show command for this device.

        Returns:
            str: BGP summary show command
        """
        return ["show bgp sum", "show bgp ipv6 unicast summary"]
