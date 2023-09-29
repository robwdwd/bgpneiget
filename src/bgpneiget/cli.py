#!/usr/bin/env python3

# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#

"""Get BGP neighbours from network devices."""
import asyncio
import csv
import json
import logging
import os
import pprint
import shutil
import sys
import tempfile
from json import JSONDecodeError

import aiosqlite
import click

from bgpneiget.devices import init_device
from bgpneiget.worker import DeviceWorker, DeviceWorkerException

pp = pprint.PrettyPrinter(indent=2, width=120)

logging.basicConfig(format="%(asctime)s %(message)s")
logger = logging.getLogger()


async def do_devices(devices: dict, prog_args: dict):
    """Process the devices in the queue.

    Args:
        devices (dict): Dictionary of devices.
        prog_args (dict): Program arguments.
    """
    supported_os = ["IOS", "IOS-XR", "IOS-XE", "JunOS", "EOS", "NX-OS"]

    queue = asyncio.Queue()
    db_lock = asyncio.Lock()

    try:
        db_con = await aiosqlite.connect(prog_args["db_file"])
        db_cursor = await db_con.cursor()
        await db_cursor.execute("DROP TABLE IF EXISTS neighbours")
        await db_cursor.execute(
            "CREATE TABLE neighbours(hostname, os, platform, remote_ip, remote_asn, ip_version, address_family, is_up, pfxrcd, state, routing_instance, protocol_instance)"
        )

        await db_con.commit()
        await db_cursor.close()
    except aiosqlite.Error as err:
        raise SystemExit(f"Failed to create new SQLite database: {err}") from err

    for device in devices.values():
        if device["protocol"] == "TELNET" and prog_args["skip_telnet"]:
            logger.info("[%s] Skipping device using telnet protocol.", device["hostname"])
            continue

        if device["os"] in supported_os:
            new_device = await init_device(device)
            await queue.put(new_device)
        else:
            logger.warning("[%s] %s is not a supported OS.", {device["hostname"]}, {device["os"]})

    # Create three worker tasks to process the queue concurrently.
    workers = []
    for i in range(3):
        worker = DeviceWorker(db_con, db_lock, queue, prog_args)
        task = asyncio.create_task(worker.run(i))
        workers.append(task)

    try:
        await asyncio.gather(*workers, return_exceptions=False)
    except DeviceWorkerException as err:
        logger.error("Worker failed can not continue: %s", err)
        for task in workers:
            task.cancel()

        await asyncio.gather(*workers, return_exceptions=True)
        await db_con.close()
        return

    # Output CSV or JSON

    db_con.row_factory = aiosqlite.Row

    async with db_con.execute("SELECT * FROM neighbours") as db_cursor:
        results = await db_cursor.fetchall()
        if prog_args["out_format"] == "json":
            print(json.dumps([dict(neighbour) for neighbour in results], indent=2, sort_keys=True))
        elif prog_args["out_format"] == "csv":
            lines = [dict(neighbour) for neighbour in results]
            writer = csv.DictWriter(
                sys.stdout,
                fieldnames=lines[0].keys(),
                dialect="unix",
                quotechar=prog_args["quotechar"],
                delimiter=prog_args["delimeter"],
            )
            writer.writeheader()
            writer.writerows(lines)

        else:
            raise SystemExit("Invalid output format.")

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
    "--ignore-private-asn",
    is_flag=True,
    help="Ignore private or reserved ASNs.",
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
@click.option(
    "--out-format",
    type=click.Choice(["json", "csv"], case_sensitive=False),
    metavar="FORMAT",
    default="json",
    help="Output format.",
)
@click.option(
    "--delimeter",
    type=str,
    metavar="DELIMETER",
    default=",",
    help="Delimeter used for CSV output.",
)
@click.option(
    "--quotechar",
    type=str,
    metavar="QUOTECHAR",
    default='"',
    help="Character used for quoting CSV fields.",
)
@click.option("--skip-telnet", is_flag=True)
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

    tmp_db_dir = tempfile.mkdtemp(prefix="bgpneiget_", suffix="_db")

    prog_args = {
        "username": cfg["username"],
        "password": cfg["password"],
        "db_file": f"{tmp_db_dir}/results.db",
        "except_as": cli_args["except_as"],
        "ignore_as": cli_args["ignore_as"],
        "ignore_private_asn": cli_args["ignore_private_asn"],
        "table": cli_args["table"],
        "with_vrfs": cli_args["with_vrfs"],
        "out_format": cli_args["out_format"],
        "delimeter": cli_args["delimeter"],
        "quotechar": cli_args["quotechar"],
        "skip_telnet": cli_args["skip_telnet"],
    }

    asyncio.run(do_devices(devices, prog_args))

    try:
        shutil.rmtree(tmp_db_dir)
    except OSError as error:
        logger.warning("Failed to remove temporary database directory, %s: %s", tmp_db_dir, error)
