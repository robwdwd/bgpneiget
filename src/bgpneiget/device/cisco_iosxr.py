# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#
"""Cisco IOS-XR class."""
import asyncio
import ipaddress
import logging
import os
import pprint
from typing import Type

from asyncssh.misc import Error as AsyncSSHError
from scrapli.driver.core import AsyncIOSXRDriver
from scrapli.exceptions import ScrapliException
from textfsm import TextFSM

from bgpneiget.device.base import BaseDevice
from bgpneiget.runcmds import get_output

pp = pprint.PrettyPrinter(indent=2, width=120)

logger = logging.getLogger()


class CiscoIOSXRDevice(BaseDevice):
    """Cisco IOS-XR devices."""

    def get_driver(self) -> Type[AsyncIOSXRDriver]:
        """Get scrapli driver for this device.

        Returns:
            Type[AsyncIOSXRDriver]: Scrapli Driver
        """
        return AsyncIOSXRDriver

    def get_bgp_cmd_global(self, table: str) -> str:
        """Get the BGP summary show command for this device.

        Returns:
            str: BGP summary show command
        """
        return f"show bgp instance all table {table} unicast"

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
            as_number = int(neighbour["NEIGH_AS"])

            if (
                prog_args["ignore_private_asn"]
                and not (1 <= as_number <= 23455)
                and not (23457 <= as_number <= 64495)
                and not (131072 <= as_number <= 4199999999)
            ):
                logger.info(
                    "[%s] Ignoring neighbour '%s', ASN '%s' is reserved or private.",
                    self.hostname,
                    neighbour["BGP_NEIGH"],
                    as_number,
                )
                continue

            if prog_args["except_as"] and (as_number not in prog_args["except_as"]):
                logger.info(
                    "[%s] Ignoring neighbour '%s', '%s' not in except AS list.",
                    self.hostname,
                    neighbour["BGP_NEIGH"],
                    as_number,
                )
                continue

            if prog_args["ignore_as"] and as_number in prog_args["ignore_as"]:
                logger.info(
                    "[%s] Ignoring neighbour '%s', '%s' in ignored AS list.",
                    self.hostname,
                    neighbour["BGP_NEIGH"],
                    as_number,
                )
                continue

            routing_instance = "default"
            if "VRF" in neighbour and neighbour["VRF"]:
                routing_instance = neighbour["VRF"]

            if routing_instance != "default" and not prog_args["with_vrfs"]:
                logger.debug(
                    "[%s] Ignoring neighbour '%s' with routing instance '%s' --with-vrfs not set.",
                    self.hostname,
                    neighbour["BGP_NEIGH"],
                    routing_instance,
                )
                continue

            addr = ipaddress.ip_address(neighbour["BGP_NEIGH"])
            logger.debug("[%s] Found neighbour %s.", self.hostname, str(addr))

            is_up = False
            pfxrcd = -1
            state = "Established"

            if neighbour["STATE_PFXRCD"].isdigit():
                is_up = True
                pfxrcd = neighbour["STATE_PFXRCD"]
            else:
                state = neighbour["STATE_PFXRCD"]

            protocol_instance = "default"
            if "BGP_INSTANCE" in neighbour and neighbour["BGP_INSTANCE"]:
                protocol_instance = neighbour["BGP_INSTANCE"]

            results.append(
                {
                    "hostname": self.hostname,
                    "os": self.os,
                    "platform": self.platform,
                    "remote_ip": str(addr),
                    "remote_asn": as_number,
                    "address_family": table,
                    "ip_version": addr.version,
                    "is_up": is_up,
                    "pfxrcd": pfxrcd,
                    "state": state,
                    "routing_instance": routing_instance,
                    "protocol_instance": protocol_instance,
                }
            )

        return results

    def parse_bgp_neighbours(self, output: str) -> list:
        """Process the BGP Neigbour output from devices through textFSM.

        Args:
            output (str): Output from network device

            filename (str): Template filename

        Returns:
            dict: BGP Neighbours
        """
        try:
            template_file = os.path.join(os.path.dirname(__file__), "../textfsm/cisco_iosxr_show_bgp.textfsm")
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
            parsed_result = await loop.run_in_executor(None, self.parse_bgp_neighbours, resp.result)
            result = result + await self.process_bgp_neighbours(parsed_result, table, prog_args)

        return result
