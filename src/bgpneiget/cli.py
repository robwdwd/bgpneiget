#!/usr/bin/env python3
"""Get BGP neighbours from network devices."""
import os
import sys
import re
import pprint
import json
import ipaddress
import click


from napalm import get_network_driver

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


def get_neighbours(host, device_os, transport="ssh"):
    """Get BGP neighbours from network device.

    Args:
        host (str): Hostname of network device.
        device_os (str): OS of the network Device.
        transport (str, optional): Network device transport type. telnet or ssh. Defaults to "ssh".

    Returns:
        dict: BGP Neighbours from device.
    """
    optional_args = {"transport": transport.lower()}

    driver = get_network_driver(device_os)
    # Connect and open the device with napalm and run commands.
    #
    try:
        with driver(host, cfg["username"], cfg["password"], optional_args=optional_args) as device:
            return device.get_bgp_neighbors()
    except Exception as error_msg:
        print("ERROR: Connecting to {} failed: {}".format(host, error_msg), file=sys.stderr)
        return None


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


def do_device(hostname, device_os, transport="ssh"):
    """Connect to device and get the neighbours.

    Args:
        hostname (str): Hostname of network device
        device_os (str): OS of the network device
        transport (str, optional): Network device transport either ssh or telnet. Defaults to "ssh".

    Returns:
        dict: BGP neighbours on device.
    """
    results = {}

    neighbours = get_neighbours(hostname, device_os, transport)

    if neighbours:
        neighbours = filter_ri(neighbours, prog_args["ri"])
        for routing_instance in neighbours:
            results[routing_instance] = parse_neighbours(neighbours[routing_instance])
    elif prog_args["verbose"] >= 1:
        print("DEBUG: No BGP neighbours found on {}".format(hostname), file=sys.stderr)

    return results


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
@click.option("--asignore", 
    type=int, metavar="ASNUM", 
    multiple=True,
    help="AS number to filter out. Can be used multiple times.")
@click.option(
    "--ri", default="global", help="Regular expressions of routing instances / vrfs to match. Default 'global'"
)
def cli(**cli_args):
    """Entry point for command.

    Raises:
        SystemExit: Error in command line options
    """
    global prog_args
    global cfg

    prog_args = cli_args

    pp.pprint(prog_args)

    cfg = json.load(prog_args["config"])

    if prog_args["asignore"] and prog_args["asexcept"]:

        raise SystemExit(
            "{} error: argument --asignore: not allowed" " with argument --asexcept".format(os.path.basename(__file__))
        )

    if prog_args["seed"] is not None and prog_args["device"] is not None:

        raise SystemExit(
            "{} error: argument --seed: not allowed" " with argument --device".format(os.path.basename(__file__))
        )

    supported_os = ["ios", "ios-xr", "junos", "eos"]

    devices_results = {}

    if prog_args["device"]:
        if prog_args["device"][1].lower() not in supported_os:
            raise SystemExit("ERROR: OS ({})is not supported.".format(prog_args["device"][1]))

        if prog_args["listri"]:
            bgp_neighbours = get_neighbours(prog_args["device"][0], prog_args["device"][1], prog_args["device"][2])
            if bgp_neighbours:
                for routing_instance in bgp_neighbours:
                    print(routing_instance)
        else:
            devices_results[prog_args["device"][0]] = do_device(
                prog_args["device"][0], prog_args["device"][1], prog_args["device"][2]
            )
            if prog_args["verbose"] >= 2:
                print("Current memory usage of results dictionary: {}".format(sys.getsizeof(devices_results)))

    elif prog_args["seed"]:
        seedline_re = re.compile("^(.+);(.+);(.+)$")

        for seed_line in prog_args["seed"]:
            seedline = str(seed_line).strip()
            seed_matches = seedline_re.match(seedline)
            if seed_matches:
                hostname = seed_matches.group(1)
                host_os = seed_matches.group(2)
                host_transport = seed_matches.group(3)

                if prog_args["verbose"] >= 2:
                    print(
                        "DEBUG: Found matching seedline {}. Device: "
                        "{}, OS: {}, Transport: {}".format(seedline, hostname, host_os, host_transport),
                        file=sys.stderr,
                    )

                if host_os in supported_os:
                    if prog_args["listri"]:
                        bgp_neighbours = get_neighbours(hostname, host_os, host_transport)
                        if bgp_neighbours:
                            print(hostname)
                            for routing_instance in bgp_neighbours:
                                print(routing_instance)
                    else:
                        devices_results[hostname] = do_device(hostname, host_os, host_transport)
                        if prog_args["verbose"] >= 2:
                            print(
                                "Current memory usage of results dictionary: {}".format(sys.getsizeof(devices_results))
                            )

                else:
                    print("WARNING: {} is not a supported OS for device {}.".format(host_os, hostname), file=sys.stderr)
            else:
                print("WARNING: Seedline not matched: {} ".format(seedline), file=sys.stderr)
    else:
        raise SystemExit("Required --seed or --device options are missing.")

    if not prog_args["listri"]:
        print(json.dumps(devices_results, indent=2))

        if prog_args["verbose"] >= 2:
            print("Current memory usage of results dictionary: {}".format(sys.getsizeof(devices_results)))
