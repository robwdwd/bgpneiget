# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#
"""Device command runner."""

from typing import Dict

from bgpneiget.device.base import BaseDevice
from bgpneiget.device.juniper import JunOsDevice


async def get_output(
    device: BaseDevice,
    cli_cmds: Dict[str, str],
    username: str,
    password: str,
    timeout: int = 60,
) -> Dict[str, str]:
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

    try:
        async with driver(**driver_options) as net_connect:
            if isinstance(driver, JunOsDevice):
                net_connect.comms_prompt_pattern = '^Iinuu0to8iewuiz>\s*$'
                response = await net_connect.send_command(command='set cli prompt Iinuu0to8iewuiz>', timeout_ops=timeout)
            for addrf in cli_cmds:
                response = await net_connect.send_command(command=cli_cmds[addrf], timeout_ops=timeout)
                result[addrf] = response.result
    except Exception as err:
        raise err

    return result
