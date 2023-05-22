# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#
"""Device command runner."""

from typing import Dict

from scrapli.exceptions import ScrapliException
from scrapli.response import MultiResponse

from bgpneiget.device.base import BaseDevice


async def get_output(
    device: BaseDevice,
    cli_cmds: Dict,
    username: str,
    password: str,
    timeout: int = 60,
) -> MultiResponse:
    """Get existing configuration from router.

    Args:
        device (BaseDevice): Device object
        cli_cmds (list): CLI commands to run
        username (str): Username to log into device
        password (str): Password to log into device
        timeout (int): Timeout

    Returns:
        MultiResponse: Device output
    """
    driver = device.get_driver()
    driver_options = device.get_driver_options(username, password)

    try:
        async with driver(**driver_options) as net_connect:
            if device.platform == "juniper_junos":
                net_connect.comms_prompt_pattern = "^Iinuu0to8iewuiz>\s*$"
                response = await net_connect.send_command(
                    command="set cli prompt Iinuu0to8iewuiz>", timeout_ops=timeout
                )

            response = await net_connect.send_commands(commands=list(cli_cmds.values()), timeout_ops=timeout)

    except ScrapliException as err:
        raise err

    return response
