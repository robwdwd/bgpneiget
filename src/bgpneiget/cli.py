#!/usr/bin/env python3

import os
import sys
import re
import pprint
import json
import argparse
import ipaddress

from napalm import get_network_driver

pp = pprint.PrettyPrinter(indent=2, width=120)

with open(os.environ['HOME'] + '/.cfg/get_bgp.json') as cfgfile:
    cfg = json.load(cfgfile)

parser = argparse.ArgumentParser()

arg_seed_group = parser.add_mutually_exclusive_group(required=True)
arg_seed_group.add_argument("-s", "--seed", type=argparse.FileType('r'),
                            help="Seedfile with devices to connect to listed one per line in format <device>;<OS>.")
arg_seed_group.add_argument("-d", "--device", nargs=3, metavar=('HOSTNAME', 'OS', 'TRANSPORT'),
                            help="Single device to connect to along with the device OS and transport (SSH or Telnet)")

parser.add_argument('--verbose', '-v', action='count', default=0,
                    help="Output some debug information, use multiple times for increased verbosity.")

parser.add_argument('--listri', action='store_true',
                    help="Lists all routing instances / vrf found on the device. Will not process the bgp neighbours.")

# Output format argumets.
arg_output_group = parser.add_argument_group(title="Output Format",
                                             description="Set the output format. "
                                             "Multiple output formats will output results multiple times.")

arg_output_group.add_argument("--json", action="store_true",
                              help="Output in json format.")
arg_output_group.add_argument("--delimited", action="store_true",
                              help="Output in delimited format.")
arg_output_group.add_argument("--delimiter", default=',',
                              help="Delimiter character to use in delimited output.")
# Filtering arguments

arg_filter_group = parser.add_argument_group(title="Filtering",
                                             description="Filtering options to control what BGP "
                                             "neighbours are included or excluded from the output.")
arg_filter_group.add_argument("--privateas", action="store_true",
                              help="Include private AS numbers.")
arg_filter_group.add_argument("--rfc1918", action="store_true",
                              help="Include neighbours with RFC1918 addresses.")
arg_filter_group.add_argument("--asexcept", nargs='*', type=int, metavar='ASNUM',
                              help="Filter out all AS number except those listed here (Seperated by space.)")
arg_filter_group.add_argument("--asignore", nargs='*', type=int, metavar='ASNUM',
                              help="AS numbers to filter out (Seperated by space.)")
arg_filter_group.add_argument("--ri", default='global',
                              help="Regular expressions of routing instances / vrfs to match. Default 'global'")

prog_args = parser.parse_args()

# pp.pprint(prog_args)


def parse_neighbours(neighbours):
    results = {}
    for neighbour in neighbours:
        addr = ipaddress.ip_address(neighbour)

        # If this is a private IP address then continue
        # unless the rfc1918 argument was given
        #
        if (not prog_args.rfc1918) and addr.is_private:
            if prog_args.verbose >= 2:
                print("DEBUG: Skipping neighbour {} with a "
                      "private IP.".format(neighbour), file=sys.stderr)
            continue

        if prog_args.verbose >= 1:
            print('DEBUG: Found neighbour {}'.format(neighbour), file=sys.stderr)

        ipversion = addr.version

        if ipversion == 4:
            address_family = 'ipv4'
            if prog_args.verbose >= 2:
                print('DEBUG: Neighbour {} has an IPv4 address.'.format(neighbour), file=sys.stderr)
        elif ipversion == 6:
            address_family = 'ipv6'
            if prog_args.verbose >= 2:
                print('DEBUG: Neighbour {} has an IPv6 address.'.format(neighbour), file=sys.stderr)
        else:
            print('ERROR: Can not find an address family for neighbour {}.'.format(neighbour), file=sys.stderr)
            continue

        as_number = neighbours[neighbour]['remote_as']

        if prog_args.asexcept and (as_number not in prog_args.asexcept):
            continue

        if prog_args.asignore and as_number in prog_args.asignore:
            continue

        results[neighbour] = {'as': as_number,
                              'description': neighbours[neighbour]['description'],
                              'ip_version': ipversion,
                              'is_up': neighbours[neighbour]['is_up'],
                              'is_enabled': neighbours[neighbour]['is_enabled'],
                              'dual_stack': False
                             }

        # Check to see if ipv4 and ipv6 is enabled on this neighbour

        if neighbours[neighbour]['is_up']:
            results[neighbour]['routes'] = {}
            results[neighbour]['routes'][address_family] = neighbours[neighbour]['address_family'][address_family]

            # IPv4 BGP neighbour with IPv6 routes.
            if ipversion == 4 and 'ipv6' in neighbours[neighbour]['address_family']:
                # If sent_prefixes is -1 then ipv6 routes are not enabled on this neighbour (mainly for JunOS)
                if neighbours[neighbour]['address_family']['ipv6']['sent_prefixes'] != -1:
                    results[neighbour]['routes']['ipv6'] = neighbours[neighbour]['address_family']['ipv6']
                    results[neighbour]['dual_stack'] = True
                    if prog_args.verbose >= 2:
                        print('DEBUG: Neighbour {} is multi-protocol.'.format(neighbour), file=sys.stderr)

            # IPv6 BGP neighbour with IPv4 routes.
            if ipversion == 6 and 'ipv4' in neighbours[neighbour]['address_family']:
                # If sent_prefixes is -1 then ipv4 routes are not enabled on this neighbour (mainly for JunOS)
                if neighbours[neighbour]['address_family']['ipv4']['sent_prefixes'] != -1:
                    results[neighbour]['routes']['ipv4'] = neighbours[neighbour]['address_family']['ipv4']
                    results[neighbour]['dual_stack'] = True
                    if prog_args.verbose >= 2:
                        print('DEBUG: Neighbour {} is multi-protocol.'.format(neighbour), file=sys.stderr)
        else:
            results[neighbour]['routes'] = None
            if prog_args.verbose >= 2:
                print('DEBUG: Neighbour {} is down.'.format(neighbour), file=sys.stderr)

    return results


def get_neighbours(host, device_os, transport='ssh'):

    optional_args = {'transport': transport.lower()}

    driver = get_network_driver(device_os)
    # Connect and open the device with napalm and run commands.
    #
    try:
        with driver(host, cfg['username'], cfg['password'], optional_args=optional_args) as device:
            return device.get_bgp_neighbors()
    except Exception as e:
        print('ERROR: Connecting to {} failed: {}'.format(host, e), file=sys.stderr)
        return None


def filter_ri(neighbours, filter_re):
    ri_re = re.compile(filter_re)

    results = {}

    for ri in neighbours:
        if ri_re.match(ri):
            if prog_args.verbose >= 1:
                print('DEBUG: Found matching routing instance {}'.format(ri), file=sys.stderr)
                results[ri] = neighbours[ri]['peers']
            else:
                if prog_args.verbose >= 2:
                    print('DEBUG: Found non matching routing instance {}'.format(ri), file=sys.stderr)

    return results


def do_device(hostname, device_os, transport='ssh'):

    results = {}

    neighbours = get_neighbours(hostname, device_os, transport)

    if neighbours:
        neighbours = filter_ri(neighbours, prog_args.ri)
        for ri in neighbours:
            results[ri] = parse_neighbours(neighbours[ri])
    elif prog_args.verbose >= 1:
        print('DEBUG: No BGP neighbours found on {}'.format(hostname), file=sys.stderr)

    return results


# Check for these two manualy as mutual exclusion would take the arguments out of the filter
# group.

if prog_args.asignore and prog_args.asexcept:
    parser.print_usage()
    raise SystemExit("{} error: argument --asignore: not allowed"
                     " with argument --asexcept".format(os.path.basename(__file__)))

supported_os = ['IOS', 'IOS-XR', 'JunOS', 'EOS']

devices_results = {}

if prog_args.device:
    if prog_args.device[1] not in supported_os:
        raise SystemExit("ERROR: OS ({})is not supported.".format(prog_args.device[1]))

    if prog_args.listri:
        bgp_neighbours = get_neighbours(prog_args.device[0], prog_args.device[1], prog_args.device[2])
        if bgp_neighbours:
            for routing_instance in bgp_neighbours:
                print(routing_instance)
    else:
        devices_results[prog_args.device[0]] = do_device(prog_args.device[0], prog_args.device[1], prog_args.device[2])
        if prog_args.verbose >= 2:
            print('Current memory usage of results dictionary: {}'.format(sys.getsizeof(devices_results)))

elif prog_args.seed:
    seedline_re = re.compile('^(.+);(.+);(.+)$')

    for sl in prog_args.seed:
        seedline = str(sl).strip()
        m = seedline_re.match(seedline)
        if m:
            hostname = m.group(1)
            host_os = m.group(2)
            host_transport = m.group(3)

            if prog_args.verbose >= 2:
                print("DEBUG: Found matching seedline {}. Device: "
                      "{}, OS: {}, Transport: {}".format(seedline, hostname, host_os, host_transport), file=sys.stderr)

            if host_os in supported_os:
                if prog_args.listri:
                    bgp_neighbours = get_neighbours(hostname, host_os, host_transport)
                    if bgp_neighbours:
                        print(hostname)
                        for routing_instance in bgp_neighbours:
                            print(routing_instance)
                else:
                    devices_results[hostname] = do_device(hostname, host_os, host_transport)
                    if prog_args.verbose >= 2:
                        print('Current memory usage of results dictionary: {}'.format(sys.getsizeof(devices_results)))

            else:
                print("WARNING: {} is not a supported OS for device {}.".format(host_os, hostname), file=sys.stderr)
        else:
            print("WARNING: Seedline not matched: {} ".format(seedline), file=sys.stderr)
else:
    raise SystemExit("Required --seed or --device options are missing.")

if not prog_args.listri:
    pp.pprint(devices_results)
    if prog_args.verbose >= 2:
        print('Current memory usage of results dictionary: {}'.format(sys.getsizeof(devices_results)))
