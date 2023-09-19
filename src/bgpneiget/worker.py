# Copyright (c) 2023, Rob Woodward. All rights reserved.
#
# This file is part of BGP Neighbour Get Tool and is released under the
# "BSD 2-Clause License". Please see the LICENSE file that should
# have been included as part of this distribution.
#

import asyncio
import logging
import pprint

import aiosqlite

from bgpneiget.device.base import BaseDevice

pp = pprint.PrettyPrinter(indent=2, width=120)

logger = logging.getLogger()


class DeviceWorkerException(Exception):
    """Device worker exception."""

    pass


class DeviceWorker:
    """Device Worker."""

    def __init__(
        self,
        db_con: aiosqlite.Connection,
        db_lock: asyncio.Lock,
        queue: asyncio.Queue,
        prog_args: dict,
    ) -> None:
        """Init.

        Args:
            db_con (aiosqlite.Connection): SQlite DB Connection
            db_lock (asyncio.Lock): Database Lock
            queue (asyncio.Queue): Queue of devices
            prog_args (dict): Program Args

        Raises:
            DeviceWorkerException: When worker does not start
        """
        self.db_con = db_con
        self.queue = queue
        self.db_lock = db_lock
        self.prog_args = prog_args
        self.db_cursor = None

    async def run(self, i: int) -> None:
        """Device worker coroutine, reads from the queue until empty."""
        try:
            # if i == 1:
            #    raise DeviceWorkerException("test")

            try:
                self.db_cursor = await self.db_con.cursor()
            except aiosqlite.Error as err:
                raise DeviceWorkerException(f"Worker {i} failed to create db cursor: {err}") from err

            while True:
                if self.queue.empty():
                    logger.info("Worker #%d finished no more items in queue.", i)
                    return

                device: BaseDevice = self.queue.get_nowait()

                result = []

                try:
                    result = await device.get_neighbours(self.prog_args)
                except Exception as err:
                    logger.exception("[%s] Device failed: %s", device.hostname, err)
                    self.queue.task_done()
                    continue

                if not result:
                    logger.info("[%s] Device has no neighbours.", device.hostname)
                    self.queue.task_done()
                    continue

                async with self.db_lock:
                    try:
                        await self.db_cursor.executemany(
                            "INSERT INTO neighbours "
                            "(hostname,os,platform,address_family,ip_version,is_up,pfxrcd,protocol_instance,remote_asn,remote_ip,routing_instance,state) "
                            "VALUES(:hostname,:os,:platform,:address_family,:ip_version,:is_up,:pfxrcd,:protocol_instance,:remote_asn,:remote_ip,:routing_instance,:state);",
                            result,
                        )
                        await self.db_con.commit()
                    except aiosqlite.Error as err:
                        logger.exception("[%s] Failed to insert result in to database: %s", device.hostname, err)

                self.queue.task_done()
        except asyncio.CancelledError:
            logger.info("Worker #%d was cancelled due to failure of other workers.", i)
            raise
        finally:
            logger.info("Worker #%d finished, running cleanup.", i)
            if self.db_cursor:
                await self.db_cursor.close()
