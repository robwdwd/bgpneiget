#!/usr/bin/env python3

# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#

"""Get BGP neighbours from network devices."""
import asyncio
import ipaddress
import json
import os
import pprint
import re
import sys
from json import JSONDecodeError

import click

from bgpneiget.device.base import BaseDevice
from bgpneiget.devices import init_device
from bgpneiget.runcmds import get_output

pp = pprint.PrettyPrinter(indent=2, width=120)

prog_args = {}
cfg = {}


def parse_neighbours(neighbours):
    """Parse the bgp neighbours from network device.

    Args:
        neighbours (dict): Neighbour list.

    Returns:
        dict: Parsed neighbour list.
    """
    results = {}
    for neighbour in neighbours:
        addr = ipaddress.ip_address(neighbour)

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

        as_number = neighbours[neighbour]["remote_as"]

        if prog_args["asexcept"] and (as_number not in prog_args["asexcept"]):
            continue

        if prog_args["asignore"] and as_number in prog_args["asignore"]:
            continue

        results[neighbour] = {
            "as": as_number,
            "description": neighbours[neighbour]["description"],
            "ip_version": ipversion,
            "is_up": neighbours[neighbour]["is_up"],
            "is_enabled": neighbours[neighbour]["is_enabled"],
            "dual_stack": False,
        }

        # Check to see if ipv4 and ipv6 is enabled on this neighbour

        if neighbours[neighbour]["is_up"]:
            results[neighbour]["routes"] = {}
            results[neighbour]["routes"][address_family] = neighbours[neighbour]["address_family"][address_family]

            # IPv4 BGP neighbour with IPv6 routes.
            if ipversion == 4 and "ipv6" in neighbours[neighbour]["address_family"]:
                # If sent_prefixes is -1 then ipv6 routes are not enabled on this neighbour (mainly for JunOS)
                if neighbours[neighbour]["address_family"]["ipv6"]["sent_prefixes"] != -1:
                    results[neighbour]["routes"]["ipv6"] = neighbours[neighbour]["address_family"]["ipv6"]
                    results[neighbour]["dual_stack"] = True
                    if prog_args["verbose"] >= 2:
                        print("DEBUG: Neighbour {} is multi-protocol.".format(neighbour), file=sys.stderr)

            # IPv6 BGP neighbour with IPv4 routes.
            if ipversion == 6 and "ipv4" in neighbours[neighbour]["address_family"]:
                # If sent_prefixes is -1 then ipv4 routes are not enabled on this neighbour (mainly for JunOS)
                if neighbours[neighbour]["address_family"]["ipv4"]["sent_prefixes"] != -1:
                    results[neighbour]["routes"]["ipv4"] = neighbours[neighbour]["address_family"]["ipv4"]
                    results[neighbour]["dual_stack"] = True
                    if prog_args["verbose"] >= 2:
                        print("DEBUG: Neighbour {} is multi-protocol.".format(neighbour), file=sys.stderr)
        else:
            results[neighbour]["routes"] = None
            if prog_args["verbose"] >= 2:
                print("DEBUG: Neighbour {} is down.".format(neighbour), file=sys.stderr)

    return results


def filter_ri(neighbours, filter_re):
    """Filter neighbours based on routing instance match.

    Args:
        neighbours (dict): Neighbours to filter.
        filter_re (str): Regular expression to match routing instance name against.

    Returns:
        dict: Neighbours matching the routing instance filter.
    """
    ri_re = re.compile(filter_re)

    results = {}

    for routing_instance in neighbours:
        if ri_re.match(routing_instance):
            results[routing_instance] = neighbours[routing_instance]["peers"]
            if prog_args["verbose"] >= 1:
                print("DEBUG: Found matching routing instance {}".format(routing_instance), file=sys.stderr)
        else:
            if prog_args["verbose"] >= 2:
                print("DEBUG: Found non matching routing instance {}".format(routing_instance), file=sys.stderr)

    return results


async def device_worker(name: str, queue: asyncio.Queue, username: str, password: str):
    """Device worker coroutine, reads from the queue until empty.

    Args:
        name (str): Name for the worker.
        queue (asyncio.Queue): AsyncIO queue
    """
    while True:
        device: BaseDevice = await queue.get() 
        pp.pprint(device.hostname)
        pp.pprint(device.get_ipv4_bgp_sum_cmd())
        try:
            command = device.get_ipv4_bgp_sum_cmd()
            response = await get_output(device, command, username, password)
            pp.pprint(response.result)
            result = await device.process_bgp_neighbours(response.result)
            pp.pprint(result)
        except Exception as err:
            print(f"ERROR: {name}, Device failed: {err}", file=sys.stderr)

        # await asyncio.sleep(2)
        queue.task_done()


async def do_devices(devices: dict, username: str, password: str):
    """Process the devices in the queue.

    Args:
        devices (dict): Dictionary of devices.
    """
    supported_os = ["IOS", "IOS-XR", "IOS-XE", "JunOS", "EOS", "NX-OS"]

    queue = asyncio.Queue()

    for device in devices.values():
        if device["os"] in supported_os:
            new_device = await init_device(device)
            await queue.put(new_device)
        else:
            print(f"WARNING: {device['os']} is not a supported OS for device {device['hostname']}.", file=sys.stderr)

    # Create three worker tasks to process the queue concurrently.
    tasks = []
    for i in range(3):
        task = asyncio.create_task(device_worker(f"worker-{i}", queue, username, password))
        tasks.append(task)

    # Wait until the queue is fully processed.
    await queue.join()

    # Cancel our worker tasks.
    for task in tasks:
        task.cancel()


@click.command()
@click.option(
    "--config",
    metavar="CONFIG_FILE",
    help="Configuaration file to load.",
    default=os.environ["HOME"] + "/.config/bgpneiget/config.json",
    envvar="BGPNEIGET_CONFIG_FILE",
    type=click.File(mode="r"),
)
@click.option(
    "--verbose", "-v", count=True, help="Output some debug information, use multiple times for increased verbosity."
)
@click.option(
    "-s",
    "--seed",
    type=click.File(mode="r"),
    help="Seedfile with devices to connect to listed one per line in format <device>;<OS>.",
)
@click.option(
    "-d",
    "--device",
    nargs=3,
    type=str,
    metavar=("HOSTNAME", "OS", "TRANSPORT"),
    help="Single device to connect to along with the device OS and transport (SSH or Telnet)",
)
@click.option(
    "--listri",
    is_flag=True,
    help="Lists all routing instances / vrf found on the device. Will not process the bgp neighbours.",
)
@click.option("--privateas", is_flag=True, help="Include private AS numbers.")
@click.option("--rfc1918", is_flag=True, help="Include neighbours with RFC1918 addresses.")
@click.option(
    "--asexcept",
    type=int,
    metavar="ASNUM",
    multiple=True,
    help="Filter out all AS number except this one. Can be used multiple times.",
)
@click.option(
    "--asignore", type=int, metavar="ASNUM", multiple=True, help="AS number to filter out. Can be used multiple times."
)
@click.option(
    "--ri", default="global", help="Regular expressions of routing instances / vrfs to match. Default 'global'"
)
def cli(**cli_args):
    """Entry point for command.

    Raises:
        SystemExit: Error in command line options
    """
    prog_args = cli_args

    cfg = json.load(prog_args["config"])

    if prog_args["asignore"] and prog_args["asexcept"]:
        raise SystemExit(
            f"{os.path.basename(__file__)} error: argument --asignore: not allowed with argument --asexcept"
        )

    if prog_args["seed"] is not None and prog_args["device"] is not None:
        raise SystemExit(
            f"{os.path.basename(__file__)} error: argument --seed: not allowed with argument --device"
        )

    if prog_args["device"]:
        if prog_args["device"][1] not in supported_os:
            raise SystemExit(f"ERROR: OS ({prog_args['device'][1]}) is not supported.")

        if prog_args["listri"]:
            bgp_neighbours = get_neighbours(prog_args["device"][0], prog_args["device"][1], prog_args["device"][2])
            if bgp_neighbours:
                for routing_instance in bgp_neighbours:
                    print(routing_instance)
        else:
            devices_results[prog_args["device"][0]] = do_device(
                prog_args["device"][0], prog_args["device"][1], prog_args["device"][2]
            )
    elif prog_args["seed"]:
        try:
            devices = json.load(prog_args["seed"])
        except JSONDecodeError as err:
            raise SystemExit(f"ERROR: Unable to decode json file: {err}") from err

        asyncio.run(do_devices(devices, cfg['username'], cfg['password']))

    else:
        raise SystemExit("Required --seed or --device options are missing.")
