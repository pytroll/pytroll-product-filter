#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (c) 2017 - 2023 Adam.Dybbroe

# Author(s):

#   Adam.Dybbroe <adam.dybbroe@smhi.se>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Posttroll runner for the product-filtering."""

import logging
import os
import shutil
from urllib.parse import urlparse

import signal
from queue import Empty
from threading import Thread

from posttroll.listener import ListenerContainer
from posttroll.message import Message
from posttroll.publisher import NoisyPublisher

from .constants import AREA_CONFIG_PATH, METOP_LETTER, METOPS
from .definitions import (
    GranuleFilter,
    InconsistentMessage,
    NoValidTles,
    SceneNotSupported,
)

LOG = logging.getLogger(__name__)


class ProductFilterRunner(Thread):
    """Product filter runner."""

    def __init__(self, options):
        """Initialize the product-filter runner."""
        super().__init__()
        self.options = options

        self.publish_topic = options['publish_topic']
        self.input_topics = options['message_types']
        self.listener = ListenerContainer(topics=self.input_topics)
        self.publisher = NoisyPublisher("product_filtering")
        self.publisher.start()
        self.loop = True
        signal.signal(signal.SIGTERM, self.signal_shutdown)

    def run(self):
        """Run the Product Filter processing."""
        while self.loop:
            file_reg = {}
            try:
                msg = self.listener.output_queue.get(timeout=1)
                LOG.debug("Message: %s", str(msg.data))
            except Empty:
                continue
            else:
                file_reg = self.start_product_filtering(file_reg, msg)
                # Cleanup in file registry (keep only the last 5):
                keys = list(file_reg.keys())
                if len(keys) > 5:
                    keys.sort()
                    file_reg.pop(keys[0])

    def start_product_filtering(self, registry, message):
        """From a posttroll/trollstalker message start the pytroll product filtering."""
        LOG.info("\nregistry dict: %s", registry)
        LOG.info("\tMessage:\n%s", message)

        # Get yaml config:
        instrument_name = message.data.get("instrument", message.data.get("instruments"))
        if instrument_name:
            section = "%s_hook" % instrument_name
            LOG.debug("Section = %s", section)

        area_def_file = os.path.join(AREA_CONFIG_PATH, "areas.yaml")
        LOG.debug("Area config file path: %s", area_def_file)
        try:
            granule_ok = GranuleFilter(self.options, area_def_file)(message)
            status_code = 0
        except (InconsistentMessage, NoValidTles, SceneNotSupported, IOError) as e__:
            LOG.exception("Could not do the granule filtering: %s", e__)
            status_code = 2

        if status_code == 2:
            return registry

        start_time = message.data["start_time"]
        scene_id = start_time.strftime("%Y%m%d%H%M")
        urlobj = urlparse(message.data["uri"])
        source_path, source_fname = os.path.split(urlobj.path)
        registry[scene_id] = os.path.join(source_path, source_fname)
        platform_name = METOPS.get(message.data["satellite"], message.data["satellite"])
        instrument = str(message.data["instruments"])
        if not granule_ok:
            LOG.info("Granule %s outside all areas", str(registry[scene_id]))
            return registry

        LOG.info("Granule %s inside one area", str(registry[scene_id]))
        mletter = METOP_LETTER.get(platform_name)
        # Now do the copying of the file to disk changing the filename!
        filename = None
        if instrument in ["iasi"]:
            # Example: iasi_b__twt_l2p_1706211005.bin
            filename = "iasi_{0}__twt_l2p_{1}.bin".format(
                mletter, start_time.strftime("%y%m%d%H%M")
            )
        elif instrument in ["ascat"]:
            # Examples:
            # ascat_b_ears250_1706211008.bin
            # ascat_a_earscoa_1706211058.bin
            product_name = str(message.data["product"])[0:3]
            filename = "ascat_{0}_ears{1}_{2}.bin".format(
                mletter, product_name, start_time.strftime("%y%m%d%H%M")
            )

        if "destination" not in self.options:
            LOG.info("Don't do anything with this file...")
            return registry

        if filename:
            dest_filepath = os.path.join(self.options["destination"], filename)
        else:
            dest_filepath = os.path.join(self.options["destination"], source_fname)

        if not os.path.exists(dest_filepath):
            shutil.copy(urlobj.path, dest_filepath)
            LOG.info("File copied from %s to %s", urlobj.path, dest_filepath)
        else:
            LOG.info("File is there (%s) already, don't copy...", os.path.dirname(dest_filepath))

        output_messages = self.get_output_messages(dest_filepath, message)

        for output_msg in output_messages:
            if output_msg:
                LOG.debug("Sending message: %s", str(output_msg))
                self.publisher.send(str(output_msg))

        return registry

    def get_output_messages(self, filepath, msg):
        """Generate the adequate output message(s) depending on if an output file was created or not."""
        return [self._generate_output_message(filepath, msg)]

    def _generate_output_message(self, filepath, input_msg):
        """Create the output message to publish."""
        output_topic = self.publish_topic
        to_send = prepare_posttroll_message(input_msg)
        to_send['uri'] = str(filepath)
        to_send['uid'] = os.path.basename(filepath)
        to_send['type'] = 'unknown'
        to_send['format'] = 'BUFR'
        pubmsg = Message(output_topic, 'file', to_send)
        return pubmsg

    def signal_shutdown(self, *args, **kwargs):
        """Shutdown the Product Filter processing."""
        self.close()

    def close(self):
        """Shutdown the Product filter processing."""
        LOG.info('Terminating the Product Filtering.')
        self.loop = False
        try:
            self.listener.stop()
        except Exception:
            LOG.exception("Couldn't stop listener.")
        if self.publisher:
            try:
                self.publisher.stop()
            except Exception:
                LOG.exception("Couldn't stop publisher.")


def prepare_posttroll_message(input_msg):
    """Create the basic posttroll-message fields and return."""
    to_send = input_msg.data.copy()
    to_send.pop('dataset', None)
    to_send.pop('collection', None)
    to_send.pop('uri', None)
    to_send.pop('uid', None)
    to_send.pop('format', None)
    to_send.pop('type', None)
    return to_send
