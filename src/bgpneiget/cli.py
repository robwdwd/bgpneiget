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
from textfsm import TextFSM

from bgpneiget.device.base import BaseDevice
from bgpneiget.devices import init_device
from bgpneiget.runcmds import get_output

pp = pprint.PrettyPrinter(indent=2, width=120)


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


async def device_worker(name: str, queue: asyncio.Queue, prog_args: dict):
    """Device worker coroutine, reads from the queue until empty.

    Args:
        name (str): Name for the worker.
        queue (asyncio.Queue): AsyncIO queue
    """
    while True:
        device: BaseDevice = await queue.get()

        try:
            result = await device.get_neighbours(prog_args)
            pp.pprint(result)

        except Exception as err:
            print(f"ERROR: {name}, Device failed: {err}", file=sys.stderr)

        queue.task_done()


async def do_devices(devices: dict, prog_args: dict):
    """Process the devices in the queue.

    Args:
        devices (dict): Dictionary of devices.
        prog_args (dict): Program arguments.
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
        task = asyncio.create_task(device_worker(f"worker-{i}", queue, prog_args))
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
    help="Json seedfile with devices to connect to.",
)
@click.option(
    "-d",
    "--device",
    nargs=3,
    type=str,
    metavar=("HOSTNAME", "OS", "TRANSPORT"),
    help="Single device to connect to along with the device OS and transport (SSH or TELNET)",
)
@click.option(
    "--listri",
    is_flag=True,
    help="Lists all routing instances / vrf found on the device. Will not process the bgp neighbours.",
)
@click.option("--with-vrfs", is_flag=True, help="Include neighbours in vrfs/routing instance.")
@click.option(
    "--except-as",
    type=int,
    metavar="ASNUM",
    multiple=True,
    help="Filter out all AS number except this one. Can be used multiple times.",
)
@click.option(
    "--ignore-as", type=int, metavar="ASNUM", multiple=True, help="AS number to filter out. Can be used multiple times."
)
@click.option(
    "--ri", default="global", help="Regular expressions of routing instances / vrfs to match. Default 'global'"
)
@click.option(
    "--table",
    type=str,
    metavar="TABLE",
    multiple=True,
    default=["ipv4", "ipv6"],
    help="Get BGP neighbours from these tables.",
)
def cli(**cli_args):
    """Entry point for command.

    Raises:
        SystemExit: Error in command line options
    """
    try:
        cfg = json.load(cli_args["config"])
    except JSONDecodeError as err:
        raise SystemExit(f"Unable to parse configuration file: {err}") from err

    if cli_args["ignore_as"] and cli_args["except_as"]:
        raise SystemExit(
            f"{os.path.basename(__file__)} error: argument --ignore-as: not allowed with argument --except-as"
        )

    if cli_args["seed"] is not None and cli_args["device"] is not None:
        raise SystemExit(f"{os.path.basename(__file__)} error: argument --seed: not allowed with argument --device")

    devices = {}

    if cli_args["device"]:
        if cli_args["listri"]:
            bgp_neighbours = get_neighbours(cli_args["device"][0], cli_args["device"][1], cli_args["device"][2])
            if bgp_neighbours:
                for routing_instance in bgp_neighbours:
                    print(routing_instance)
        else:
            devices = {
                cli_args["device"][0]: {
                    "hostname": cli_args["device"][0],
                    "os": cli_args["device"][1],
                    "protocol": cli_args["device"][2],
                }
            }

    elif cli_args["seed"]:
        try:
            devices = json.load(cli_args["seed"])
        except JSONDecodeError as err:
            raise SystemExit(f"ERROR: Unable to decode json file: {err}") from err

    else:
        raise SystemExit("Required --seed or --device options are missing.")

    prog_args = {
        "username": cfg["username"],
        "password": cfg["password"],
        "except_as": cli_args["except_as"],
        "ignore_as": cli_args["ignore_as"],
        "table": cli_args["table"],
        "with_vrfs": cli_args["with_vrfs"],
        "verbose": cli_args["verbose"],
    }

    asyncio.run(do_devices(devices, prog_args))
