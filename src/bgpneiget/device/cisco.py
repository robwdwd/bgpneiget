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

pp = pprint.PrettyPrinter(indent=2, width=120)


class CiscoDevice(BaseDevice):
    """Base class for all Cisco Devices"""

    async def process_bgp_neighbours(self, output: str, prog_args: dict) -> list:
        fsm: TextFSM = prog_args["fsm"]
        pp.pprint(fsm)
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, fsm.ParseText, output)

        pp.pprint(result)

        results = {}
        for neighbour in result:
            addr = ipaddress.ip_address(neighbour[3])

            # If this is a private IP address then continue
            # unless the rfc1918 argument was given
            #
            if (not prog_args["rfc1918"]) and addr.is_private:
                if prog_args["verbose"] >= 2:
                    print("DEBUG: Skipping neighbour {} with a " "private IP.".format(neighbour), file=sys.stderr)
                continue

            if prog_args["verbose"] >= 1:
                print("DEBUG: Found neighbour {}".format(neighbour), file=sys.stderr)

            ipversion = addr.version

            if ipversion == 4:
                address_family = "ipv4"
                if prog_args["verbose"] >= 2:
                    print("DEBUG: Neighbour {} has an IPv4 address.".format(neighbour), file=sys.stderr)
            elif ipversion == 6:
                address_family = "ipv6"
                if prog_args["verbose"] >= 2:
                    print("DEBUG: Neighbour {} has an IPv6 address.".format(neighbour), file=sys.stderr)
            else:
                print("ERROR: Can not find an address family for neighbour {}.".format(neighbour), file=sys.stderr)
                continue

            as_number = int(neighbour[4])

            if prog_args["except_as"] and (as_number not in prog_args["except_as"]):
                continue

            if prog_args["ignore_as"] and as_number in prog_args["ignore_as"]:
                continue

            is_up = False
            if neighbour[6].isdigit():
              is_up = True
              
            routing_instance = 'global'
            if neighbour[2]:
              routing_instance =  neighbour[2]

            results[str(addr)] = {
                "as": as_number,
                "ip_version": ipversion,
                "is_up": is_up,
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

    def get_ipv4_bgp_sum_cmd(self) -> str:
        """Get the BGP summary show command for this device.

        Returns:
            str: BGP summary show command
        """
        return "show ip bgp sum"

    def get_ipv6_bgp_sum_cmd(self) -> str:
        """Get the BGP summary show command for this device.

        Returns:
            str: BGP summary show command
        """
        return "show bgp ipv6 unicast summary"


class CiscoIOSXRDevice(CiscoDevice):
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
        return "show bgp sum wide"

    def get_ipv6_bgp_sum_cmd(self) -> str:
        """Get the BGP summary show command for this device.

        Returns:
            str: BGP summary show command
        """
        return "show bgp ipv6 unicast summary wide"


class CiscoNXOSDevice(CiscoDevice):
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

    def get_ipv6_bgp_sum_cmd(self) -> str:
        """Get the BGP summary show command for this device.

        Returns:
            str: BGP summary show command
        """
        return "show bgp ipv6 unicast summary"
