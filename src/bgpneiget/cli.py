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
import sys
import tempfile
from json import JSONDecodeError
from typing import Union

import aiosqlite
import click

from bgpneiget.devices import init_device
from bgpneiget.worker import DeviceWorker, DeviceWorkerException

pp = pprint.PrettyPrinter(indent=2, width=120)

logging.basicConfig(format="%(asctime)s %(message)s")
logger = logging.getLogger()


async def setup_database(db_file: str) -> aiosqlite.Connection:
    try:
        db_con = await aiosqlite.connect(db_file)
        db_cursor = await db_con.cursor()
        await db_cursor.execute("DROP TABLE IF EXISTS neighbours")
        await db_cursor.execute(
            "CREATE TABLE neighbours(hostname, os, platform, remote_ip, remote_asn, ip_version, address_family, is_up, pfxrcd, state, routing_instance, protocol_instance)"
        )
        await db_con.commit()
        await db_cursor.close()
        return db_con
    except aiosqlite.Error as err:
        raise SystemExit(f"Failed to create new SQLite database: {err}") from err


async def output_results(db_con: aiosqlite.Connection, out_format: str, quotechar: str, delimiter: str):
    db_con.row_factory = aiosqlite.Row
    async with db_con.execute("SELECT * FROM neighbours") as db_cursor:
        results = await db_cursor.fetchall()
        if out_format == "json":
            print(json.dumps([dict(neighbour) for neighbour in results], indent=2, sort_keys=True))
        elif out_format == "csv":
            lines = [dict(neighbour) for neighbour in results]
            writer = csv.DictWriter(
                sys.stdout,
                fieldnames=lines[0].keys(),
                dialect="unix",
                quotechar=quotechar,
                delimiter=delimiter,
            )
            writer.writeheader()
            writer.writerows(lines)
        else:
            raise SystemExit("Invalid output format.")


async def do_devices(devices: dict, prog_args: dict):
    """
    Process devices concurrently, store results in a SQLite database, and output in JSON or CSV format.

    Args:
        devices (dict): Dictionary of devices to process.
        prog_args (dict): Program arguments including database file, output format, and other settings.

    Raises:
        SystemExit: If there is an error creating the SQLite database or an invalid output format is specified.
    """

    supported_os = ["IOS", "IOS-XR", "IOS-XE", "JunOS", "EOS", "NX-OS"]

    queue = asyncio.Queue()
    db_lock = asyncio.Lock()

    db_con = await setup_database(prog_args["db_file"])

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
    workers = [asyncio.create_task(DeviceWorker(db_con, db_lock, queue, prog_args).run(i)) for i in range(3)]

    try:
        await asyncio.gather(*workers, return_exceptions=False)
    except DeviceWorkerException as err:
        logger.error("Worker failed can not continue: %s", err)
        for task in workers:
            task.cancel()

        await asyncio.gather(*workers, return_exceptions=True)
        await db_con.close()
        return

    await output_results(db_con, prog_args["out_format"], prog_args["quotechar"], prog_args["delimeter"])
    await db_con.close()



def load_config(config_file_cli: Union[str, None]) -> dict:
    """
    Loads and parses a configuration file using JSON.

    Args:
        config_file_cli (str): Command line location of the config file if specified.

    Returns:
        dict: The parsed configuration data.

    Raises:
        SystemExit: If there is an error parsing the configuration file.
    """

    config_file_paths = [
        config_file_cli,
        f"{os.environ.get('HOME', '')}/.config/bgpneiget/config.json",
        "/etc/bgpneiget/config.json",
    ]

    for path in config_file_paths:
        if path and os.path.isfile(path):
            with open(path, "r") as config_file:
                try:
                    return json.load(config_file)
                except JSONDecodeError as err:
                    raise SystemExit(f"Unable to parse configuration file: {err}") from err

    raise SystemExit("Unable to find any configuration file")


def check_mutually_exclusive_options(cli_args: dict):
    """
    Check for mutually exclusive options in the command-line arguments.

    Args:
        cli_args (dict): Dictionary containing command-line arguments.

    Raises:
        SystemExit: If mutually exclusive options are provided in the command-line arguments.
    """

    if cli_args["ignore_as"] and cli_args["except_as"]:
        raise SystemExit(
            f"{os.path.basename(__file__)} error: argument --ignore-as: not allowed with argument --except-as"
        )
    if cli_args["seed"] is not None and cli_args["device"] is not None:
        raise SystemExit(f"{os.path.basename(__file__)} error: argument --seed: not allowed with argument --device")


def setup_devices(cli_args: dict) -> dict:
    """
    Setup devices based on command-line arguments.

    Args:
        cli_args (dict): Dictionary containing command-line arguments.

    Returns:
        dict: Dictionary of devices with hostname, OS, and protocol.

    Raises:
        SystemExit: If required --seed or --device options are missing or there is an error decoding the JSON seed file.
    """

    if cli_args["device"]:
        return {
            cli_args["device"][0]: {
                "hostname": cli_args["device"][0],
                "os": cli_args["device"][1],
                "protocol": cli_args["device"][2],
            }
        }
    elif cli_args["seed"]:
        try:
            return json.load(cli_args["seed"])
        except JSONDecodeError as err:
            raise SystemExit(f"ERROR: Unable to decode json file: {err}") from err
    else:
        raise SystemExit("Required --seed or --device options are missing.")


@click.command()
@click.option(
    "--config",
    metavar="CONFIG_FILE",
    help="Configuaration file to load.",
    envvar="BGPNEIGET_CONFIG_FILE",
    type=str,
    required=False,
)
@click.option(
    "--loglevel",
    "-L",
    type=str,
    default="WARNING",
    help="Set logging level.",
)
@click.option(
    "--username",
    type=str,
    required=False,
    metavar="USERNAME",
    help="Username to log into routers",
    envvar="BGPNEIGET_USERNAME",
)
@click.option(
    "--password",
    type=str,
    required=False,
    metavar="PASSWORD",
    help="Password to log into routers",
    envvar="BGPNEIGET_PASSWORD",
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

    cfg = load_config(cli_args["config"])
    check_mutually_exclusive_options(cli_args)

    logger.setLevel(cli_args["loglevel"].upper())
    devices = {}

    devices = setup_devices(cli_args)

    with tempfile.TemporaryDirectory(prefix="bgpneiget_", suffix="_db", ignore_cleanup_errors=False) as tmp_db_dir:

        # Override any configuration file user name and password with command line
        # options
        if cli_args["username"]:
            cfg["username"] = cli_args["username"]

        if cli_args["password"]:
            cfg["password"] = cli_args["password"]

        if not cfg["password"] or not cfg["username"]:
            raise SystemExit("Could not find a username and password from the command line or configuration file.")

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

