# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of Looking Glass Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#
"""Device command runner."""
from typing import Union

from scrapli import AsyncScrapli
from scrapli.response import MultiResponse, Response


def setup_device_args(device: dict, username: str, password: str) -> dict:
    """Set up some default device arguments.

    Args:
        hostname (str): Hostname of device
        device_type (str): Type of device

    Returns:
        dict: Host args
    """

    return {
        "platform": device['os'],
        "host": device['hostname'],
        "auth_strict_key": False,
        "transport": "asyncssh",
        "auth_username": username,
        "auth_password": password,
    }


async def get_output(
    device: dict,
    username: str,
    password, str,
    cli_cmds: Union[list[str], str],
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
    host = setup_device_args(device, username, password)

    try:
        async with AsyncScrapli(**host) as net_connect:
            if type(cli_cmds) is str:
                response = await net_connect.send_command(command=cli_cmds, timeout_ops=timeout)
            else:
                response = await net_connect.send_commands(commands=cli_cmds, timeout_ops=timeout)
    except Exception as err:
        raise err

    return response

