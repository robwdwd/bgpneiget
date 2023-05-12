# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of Looking Glass Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#
"""Device command runner."""
import pprint
from typing import Union

from scrapli import AsyncScrapli
from scrapli.response import MultiResponse, Response

from bgpneiget.device.base import BaseDevice

pp = pprint.PrettyPrinter(indent=2, width=120)

async def get_output(
    device: BaseDevice,
    cli_cmds: Union[str, list],
    username: str,
    password: str,
    timeout: int = 60,
) -> Union[MultiResponse, Response]:
    """Get existing configuration from router.

    Args:
        hostname (str): Device hostname
        device_type (str): Type of device
        cli_cmds (list | str): CLI commands to run
        timeout (int): Timeout

    Returns:
        MultiResponse | Response: Device output
    """
    driver = device.get_driver()
    pp.pprint(driver)

    try:
        async with driver(**device.setup_device_args(username, password)) as net_connect:
            if type(cli_cmds) is str:
                response = await net_connect.send_command(command=cli_cmds, timeout_ops=timeout)
            else:
                response = await net_connect.send_commands(commands=cli_cmds, timeout_ops=timeout)
    except Exception as err:
        raise err

    return response


