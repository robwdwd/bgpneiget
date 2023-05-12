# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#
from typing import Type

from scrapli.driver.core import AsyncEOSDriver

from bgpneiget.device.base import BaseDevice


class EOSDevice(BaseDevice):

    def get_driver(self)-> Type[AsyncEOSDriver]:
        return AsyncEOSDriver