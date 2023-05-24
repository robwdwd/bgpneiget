#!/usr/bin/env python3

# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#

"""Get BGP neighbours from network devices."""
import asyncio
import json
import logging
import os
import pprint
import re
from json import JSONDecodeError

import aiosqlite
import click

from bgpneiget.device.base import BaseDevice
from bgpneiget.devices import init_device

pp = pprint.PrettyPrinter(indent=2, width=120)

logging.basicConfig(format="%(asctime)s %(message)s")
logger = logging.getLogger()


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
            logger.debug("DEBUG: Found matching routing instance %s", routing_instance)
        else:
            logger.debug("DEBUG: Found non matching routing instance %s", routing_instance)

    return results


async def device_worker(name: str, queue: asyncio.Queue, db_con: aiosqlite.Connection, db_cursor: aiosqlite.Cursor, db_lock: asyncio.Lock, prog_args: dict):
    """Device worker coroutine, reads from the queue until empty.

    Args:
        name (str): Name for the worker.
        queue (asyncio.Queue): AsyncIO queue
    """
    while True:
        device: BaseDevice = await queue.get()

        try:
            result = await device.get_neighbours(prog_args)

            async with db_lock:
              await db_cursor.executemany("INSERT INTO neighbours VALUES(:hostname,:address_family,:ip_version,:is_up,:pfxrcd,:protocol_instance,:remote_asn,:remote_ip,:routing_instance,:state);", result)
              await db_con.commit()

        except Exception as err:
            logger.exception("%s: Device failed: %s", device.hostname, err)

        queue.task_done()

        


async def do_devices(devices: dict, prog_args: dict):
    """Process the devices in the queue.

    Args:
        devices (dict): Dictionary of devices.
        prog_args (dict): Program arguments.
    """
    supported_os = ["IOS", "IOS-XR", "IOS-XE", "JunOS", "EOS", "NX-OS"]

    queue = asyncio.Queue()
    db_lock = asyncio.Lock()

    db_con = await aiosqlite.connect(prog_args["db_file"])
    db_cursor = await db_con.cursor()
    await db_cursor.execute("DROP TABLE IF EXISTS neighbours")
    await db_cursor.execute(
        "CREATE TABLE neighbours(hostname, remote_ip, remote_asn, ip_version, address_family, is_up, pfxrcd, state, routing_instance, protocol_instance)"
    )

    for device in devices.values():
        if device["os"] in supported_os:
            new_device = await init_device(device)
            await queue.put(new_device)
        else:
            logger.warning("%s is not a supported OS for device %s.", {device["os"]}, {device["hostname"]})

    # Create three worker tasks to process the queue concurrently.
    tasks = []
    for i in range(3):
        task = asyncio.create_task(device_worker(f"worker-{i}", queue, db_con, db_cursor, db_lock, prog_args))
        tasks.append(task)

    # Wait until the queue is fully processed.
    await queue.join()

    # Cancel our worker tasks.
    for task in tasks:
        task.cancel()

    await db_cursor.close()
    await db_con.close()

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
    "--loglevel",
    "-L",
    type=str,
    default="WARNING",
    help="Set logging level.",
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

    logger.setLevel(cli_args["loglevel"].upper())
    devices = {}

    if cli_args["device"]:
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
        "db_file": cfg["db_file"],
        "except_as": cli_args["except_as"],
        "ignore_as": cli_args["ignore_as"],
        "table": cli_args["table"],
        "with_vrfs": cli_args["with_vrfs"],
    }

    asyncio.run(do_devices(devices, prog_args))
