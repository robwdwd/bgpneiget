# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#
"""Device command runner."""

from typing import Dict

from scrapli.response import Response

from bgpneiget.device.base import BaseDevice


async def get_output(
    device: BaseDevice,
    cli_cmds: Dict[str, str],
    username: str,
    password: str,
    timeout: int = 60,
) -> Dict[str, Response]:
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

    result = {}

    print(driver)

    try:
        async with driver(**driver_options) as net_connect:
            for addrf in cli_cmds:
                print(addrf)
                response = await net_connect.send_command(command=cli_cmds[addrf], timeout_ops=timeout)
                result[addrf] = response.result
    except Exception as err:
        raise err

    return result
