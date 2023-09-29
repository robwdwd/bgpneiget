# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#
"""Juniper device class."""
import ipaddress
import logging
import pprint
import re
from typing import Type

import xmltodict
from asyncssh.misc import Error as AsyncSSHError
from scrapli.driver.core import AsyncJunosDriver
from scrapli.exceptions import ScrapliException

from bgpneiget.device.base import BaseDevice
from bgpneiget.runcmds import get_output

pp = pprint.PrettyPrinter(indent=2, width=120)

logger = logging.getLogger()


class JunOsDevice(BaseDevice):
    """Juniper JunOS devices."""

    AF_MAP = {
        "inet": "ipv4",
        "inet6": "ipv6",
        "l3vpn-inet6": "vpnv6",
        "l3vpn": "vpnv4",
        "inet-unicast": "ipv4",
        "inet6-unicast": "ipv6",
        "inet6-labeled-unicast": "ipv6",
        "inet-flow": "flowv4",
    }

    def get_driver(self) -> Type[AsyncJunosDriver]:
        """Get scrapli driver for this device.

        Returns:
            Type[AsyncJunosDriver]: Scrapli Driver
        """
        return AsyncJunosDriver

    def get_bgp_cmd_global(self, table: str = "ipv4") -> str:
        """Get the BGP summary show command for this device.

        Returns:
            str: BGP summary show command
        """
        return "show bgp neighbor | display xml"

    def get_default_neighbour_dict(self) -> dict:
        """Get default new neighbour structure.

        Returns:
            dict: New neighbour
        """
        return {
            "hostname": self.hostname,
            "os": self.os,
            "platform": self.platform,
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

    def process_up_neighbour(self, bgp_peer: dict, new_neighbour: dict, prog_args: dict) -> list:
        """Process establised BGP neighbour.

        Args:
            bgp_peer (dict): BGP Peer data
            new_neighbour (dict): Semi-parsed BGP neighbour

        Returns:
            list: List of new neighbours found
        """
        results = []

        new_neighbour["is_up"] = True
        # BGP RIB must exist, check for different address families and
        # routing instances here.
        if "bgp-rib" in bgp_peer:
            if isinstance(bgp_peer["bgp-rib"], dict):
                rib = self.parse_bgp_rib(bgp_peer["bgp-rib"], new_neighbour["remote_ip"])
                if rib["address_family"] != "":
                    new_neighbour["address_family"] = rib["address_family"]
                    new_neighbour["routing_instance"] = rib["routing_instance"]
                    new_neighbour["pfxrcd"] = rib["pfxrcd"]
                    results.append(new_neighbour)

            elif isinstance(bgp_peer["bgp-rib"], list):
                for table in bgp_peer["bgp-rib"]:
                    rib = self.parse_bgp_rib(table, new_neighbour["remote_ip"])
                    if rib["address_family"] != "":
                        new_nei = new_neighbour.copy()
                        new_nei["address_family"] = rib["address_family"]
                        new_nei["routing_instance"] = rib["routing_instance"]
                        new_nei["pfxrcd"] = rib["pfxrcd"]
                        results.append(new_nei)
        else:
            results.append(new_neighbour)

        return self.filter_neighbours(results, prog_args)

    def process_down_neighbour(self, bgp_peer: dict, new_neighbour: dict, prog_args: dict) -> list:
        """Process a down BGP neighbour.

        Args:
            bgp_peer (dict): BGP Peer data
            new_neighbour (dict): Semi-parsed new neighbour structure

        Returns:
            list: List of new neighbours found
        """
        results = []
        # Check if address family can be found in bgp-option-information
        # as a starting base.
        if "bgp-option-information" in bgp_peer and "address-families" in bgp_peer["bgp-option-information"]:
            address_families = bgp_peer["bgp-option-information"]["address-families"].split()
            for address_family in address_families:
                new_nei = new_neighbour.copy()
                try:
                    new_nei["address_family"] = self.AF_MAP[address_family]
                    results.append(new_nei)
                except KeyError:
                    logger.info(
                        "[%s] Down Neighbour '%s' has unparsable address family: %s",
                        self.hostname,
                        new_neighbour["remote_ip"],
                        address_family,
                    )
        else:
            results.append(new_neighbour)

        return self.filter_neighbours(results, prog_args)

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
            # Get remote IP address.
            remote_ip: str = bgp_peer["peer-address"]
            if "+" in remote_ip:
                remote_ip = remote_ip[0 : remote_ip.find("+")]

            remote_asn = int(bgp_peer["peer-as"])

            if (
                prog_args["ignore_private_asn"]
                and not (1 <= remote_asn <= 23455)
                and not (23457 <= remote_asn <= 64495)
                and not (131072 <= remote_asn <= 4199999999)
            ):
                logger.info(
                    "[%s] Ignoring neighbour '%s', ASN '%s' is reserved or private.",
                    self.hostname,
                    remote_ip,
                    remote_asn,
                )
                continue

            if prog_args["except_as"] and (remote_asn not in prog_args["except_as"]):
                logger.info(
                    "[%s] Ignoring neighbour '%s', '%s' not in except AS list.",
                    self.hostname,
                    remote_ip,
                    remote_asn,
                )
                continue

            if prog_args["ignore_as"] and remote_asn in prog_args["ignore_as"]:
                logger.info(
                    "[%s] Ignoring neighbour '%s', '%s' in ignored AS list.",
                    self.hostname,
                    remote_ip,
                    remote_asn,
                )
                continue

            new_neighbour = self.get_default_neighbour_dict()

            new_neighbour["remote_ip"] = remote_ip
            new_neighbour["remote_asn"] = remote_asn
            new_neighbour["state"] = bgp_peer["peer-state"]
            new_neighbour["ip_version"] = ipaddress.ip_address(remote_ip).version

            # Get base routing instance, this can be overwriten by the RIB parse.
            new_neighbour["routing_instance"] = (
                "default" if bgp_peer["peer-fwd-rti"] == "master" else bgp_peer["peer-fwd-rti"]
            )

            if bgp_peer["peer-state"] == "Established":
                nei_results = self.process_up_neighbour(bgp_peer, new_neighbour, prog_args)
                results = results + nei_results
            else:
                nei_results = self.process_down_neighbour(bgp_peer, new_neighbour, prog_args)
                results = results + nei_results

        return results

    def filter_neighbours(self, nei_results: list, prog_args: dict) -> list:
        """Filter found neighbours based on cli options.

        Args:
            nei_results (list): List of found neighbours
            prog_args (dict): Program arguments

        Returns:
            list: Filtered neighbours
        """
        filtered_results = []
        for neighbour in nei_results:
            if neighbour["address_family"] not in prog_args["table"]:
                logger.debug(
                    "[%s] Ignoring neighbour '%s' with unrequested address family '%s'.",
                    self.hostname,
                    neighbour["remote_ip"],
                    neighbour["address_family"],
                )
                continue

            if neighbour["routing_instance"] != "default" and not prog_args["with_vrfs"]:
                logger.debug(
                    "[%s] Ignoring neighbour '%s' with routing instance '%s' --with-vrfs not set.",
                    self.hostname,
                    neighbour["remote_ip"],
                    neighbour["routing_instance"],
                )
                continue

            filtered_results.append(neighbour)

        return filtered_results

    def parse_bgp_rib(
        self,
        rib: dict,
        ipaddr: str,
    ) -> dict:
        """Parse BGP RIB data for establised BGP Neighbour.

        Args:
            rib (dict): Rib entry
            ipaddr (str): Neighbour remote IP address

        Returns:
            dict: _description_
        """
        result = {"address_family": "", "routing_instance": "", "pfxrcd": -1}

        result["pfxrcd"] = rib["accepted-prefix-count"]

        family = rib["name"].rsplit(".")
        address_family = ""
        if len(family) == 2:
            address_family = family[0]
            result["routing_instance"] = "default"
        elif len(family) == 3:
            address_family = family[1]
            result["routing_instance"] = family[0]
        else:
            logger.info("[%s] Neighbour '%s' has unparsable address family: %s", self.hostname, ipaddr, rib["name"])
            return result

        if address_family:
            try:
                result["address_family"] = self.AF_MAP[address_family]
            except KeyError:
                logger.info(
                    "[%s] Neighbour '%s' has unparsable address family: %s", self.hostname, ipaddr, address_family
                )
                return result

        return result

    async def get_neighbours(self, prog_args: dict) -> list:
        """Get BGP neighbours from device.

        Args:
            prog_args (dict): Program arguments

        Returns:
            dict: Found BGP neighbours
        """
        commands = {}
        result = []

        commands["all"] = self.get_bgp_cmd_global()

        try:
            response = await get_output(self, commands, prog_args["username"], prog_args["password"])
        except (AsyncSSHError, ScrapliException) as err:
            logger.error("[%s] Can not get neighbours from device: %s", self.hostname, err)
            return result

        for resp in response:
            stripped_response = re.search(r"(?sm)\<.*\>", resp.result).group()
            try:
                result = result + await self.process_bgp_neighbours(stripped_response, prog_args)
            except Exception:
                logger.error("[%s] Unable to parse XML output, maybe no neigbhbours.", self.hostname)
                return result

        return result
