# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#
"""Cisco IOS-XE class."""
import asyncio
import ipaddress
import logging
import os
import pprint
from typing import Type

from asyncssh.misc import Error as AsyncSSHError
from scrapli.driver.core import AsyncIOSXEDriver
from scrapli.exceptions import ScrapliException
from textfsm import TextFSM

from bgpneiget.device.base import BaseDevice
from bgpneiget.runcmds import get_output

pp = pprint.PrettyPrinter(indent=2, width=120)
logger = logging.getLogger()


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
            return "show ip bgp vpnv4 all neighbors | include BGP neighbor is | Prefixes | BGP state | For address | Connections established"
        elif table == "vpnv6":
            return "show bgp vpnv6 unicast all neighbors | include BGP neighbor is | Prefixes | BGP state | For address | Connections established"
        else:
            raise ValueError("Unknown routing table.")

    async def process_bgp_neighbours_vpn(self, result: list, table: str, prog_args: dict) -> list:
        """Process the BGP Neigbour output from devices through textFSM.

        Args:
            result (list): Parsed output from network device
            table (str): Forwarding table (ipv4, ipv6, vpnv4 or vpnv6)
            prog_args (dict): Program arguments, asignore etc.

        Returns:
            list: BGP Neighbours
        """
        results = []
        for neighbour in result:
            addr = ipaddress.ip_address(neighbour["BGP_NEIGH"])
            remote_ip = str(addr)

            logger.debug("[%s] Found neighbour %s.", self.hostname, neighbour)

            if not neighbour["ADDRESS_FAMILY"]:
                self.log_ignored_neighbour(self.hostname, remote_ip, "No address family")
                continue

            if neighbour["ADDRESS_FAMILY"] in ("IPv4 Unicast", "IPv6 Unicast"):
                self.log_ignored_neighbour(self.hostname, remote_ip, "Non VPN IPv4 or IPv6 address family")
                continue

            if (neighbour["ADDRESS_FAMILY"] == "VPNv4 Unicast" and table == "vpnv6") or (
                neighbour["ADDRESS_FAMILY"] == "VPNv6 Unicast" and table == "vpnv4"
            ):
                self.log_ignored_neighbour(
                    self.hostname,
                    remote_ip,
                    f"{neighbour['ADDRESS_FAMILY']} neighbour but {table} address family requested",
                )
                continue

            remote_asn = int(neighbour["NEIGH_AS"])

            if not self.validate_asn(prog_args, remote_ip, remote_asn):
                continue

            routing_instance = neighbour["VRF"] if neighbour["VRF"] != "remote" else "default"
            
            if routing_instance != "default" and not prog_args["with_vrfs"]:
                self.log_ignored_neighbour(
                    self.hostname, remote_ip, f"Found routing instance '{routing_instance}' --with-vrfs not set"
                )
                continue

            is_up = neighbour["STATE"] == "Established"
            pfxrcd = neighbour["PREFIXES"] if is_up else -1
            state = "Established" if is_up else neighbour["STATE"]

            results.append(
                {
                    "hostname": self.hostname,
                    "os": self.os,
                    "platform": self.platform,
                    "remote_ip": remote_ip,
                    "remote_asn": remote_asn,
                    "address_family": table,
                    "ip_version": addr.version,
                    "is_up": is_up,
                    "pfxrcd": pfxrcd,
                    "state": state,
                    "routing_instance": routing_instance,
                    "protocol_instance": "default",
                }
            )

        return results

    async def process_bgp_neighbours(self, result: list, table: str, prog_args: dict) -> list:
        """Process the BGP Neigbour output from devices through textFSM.

        Args:
            result (list): Parsed output from network device
            table (str): Forwarding table (ipv4, ipv6, vpnv4 or vpnv6)
            prog_args (dict): Program arguments, asignore etc.

        Returns:
            list: BGP Neighbours
        """
        results = []
        for neighbour in result:
            addr = ipaddress.ip_address(neighbour["BGP_NEIGH"])
            remote_ip = str(addr)

            logger.debug("[%s] Found neighbour %s.", self.hostname, remote_ip)

            remote_asn = int(neighbour["NEIGH_AS"])

            if not self.validate_asn(prog_args, remote_ip, remote_asn):
                continue

            is_up = neighbour["STATE_PFXRCD"].isdigit()
            pfxrcd = neighbour["STATE_PFXRCD"] if is_up else -1
            state = "Established" if is_up else neighbour["STATE_PFXRCD"]

            results.append(
                {
                    "hostname": self.hostname,
                    "os": self.os,
                    "platform": self.platform,
                    "remote_ip": remote_ip,
                    "remote_asn": remote_asn,
                    "address_family": table,
                    "ip_version": addr.version,
                    "is_up": is_up,
                    "pfxrcd": pfxrcd,
                    "state": state,
                    "routing_instance": "default",
                    "protocol_instance": "default",
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
        result = []

        for table in prog_args["table"]:
            cmd = self.get_bgp_cmd_global(table)
            commands[table] = cmd
            reverse_commands[cmd] = table

        try:
            response = await get_output(self, commands, prog_args["username"], prog_args["password"])
        except (AsyncSSHError, ScrapliException) as err:
            logger.error("[%s] Can not get neighbours from device: %s", self.hostname, err)
            return result

        loop = asyncio.get_running_loop()

        for resp in response:
            table = reverse_commands[resp.channel_input]
            if table in ("vpnv4", "vpnv6"):
                template_file = "cisco_iosxe_show_bgp_vrf.textfsm"
                parsed_result = await loop.run_in_executor(None, self.parse_bgp_neighbours, resp.result, template_file)

                result = result + await self.process_bgp_neighbours_vpn(parsed_result, table, prog_args)
            else:
                template_file = "cisco_iosxe_show_bgp.textfsm"
                parsed_result = await loop.run_in_executor(None, self.parse_bgp_neighbours, resp.result, template_file)

                result = result + await self.process_bgp_neighbours(parsed_result, table, prog_args)

        return result
