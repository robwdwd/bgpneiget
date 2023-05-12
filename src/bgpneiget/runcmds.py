# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#
"""Device command runner."""
import pprint
from typing import List, Union

from scrapli.response import MultiResponse, Response

from bgpneiget.device.base import BaseDevice

pp = pprint.PrettyPrinter(indent=2, width=120)


async def get_output(
    device: BaseDevice,
    cli_cmds: Union[str, List[str]],
    username: str,
    password: str,
    timeout: int = 60,
) -> Union[MultiResponse, Response]:
    """Get existing configuration from router.

    Args:
        device (BaseDevice): Device object
        cli_cmds (list | str): CLI commands to run
        username (str): Username to log into device
        password (str): Password to log into device
        timeout (int): Timeout

    Returns:
        MultiResponse | Response: Device output
    """
    driver = device.get_driver()
    driver_options = device.get_driver_options(username, password)
    pp.pprint(driver)

    try:
        async with driver(**driver_options) as net_connect:
            if type(cli_cmds) is str:
                response = await net_connect.send_command(command=cli_cmds, timeout_ops=timeout)
            else:
                response = await net_connect.send_commands(commands=cli_cmds, timeout_ops=timeout)
    except Exception as err:
        raise err

    return response
