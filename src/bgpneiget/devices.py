# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#
"""Useful functions for mapping devices."""

from typing import Type

from bgpneiget.device.arista import EOSDevice
from bgpneiget.device.base import BaseDevice
from bgpneiget.device.cisco import IOSDevice, IOSXRDevice
from bgpneiget.device.juniper import JunOsDevice

DEVICE_TYPE_MAP = {
    "IOS": IOSDevice,
    "IOS-XR": IOSXRDevice,
    "IOS-XE": IOSDevice,
    "JunOS": JunOsDevice,
    "EOS": EOSDevice,
}


def init_device(device: dict) -> Type[BaseDevice]:
    """Initiase the device into the right class based on the OS.

    Args:
        device (dict): Device data

    Returns:
        Type[BaseDevice]: The device type
    """

    return DEVICE_TYPE_MAP[device["os"]](device)
