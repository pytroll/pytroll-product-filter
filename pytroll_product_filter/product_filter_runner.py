#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (c) 2017, 2018, 2019 Adam.Dybbroe

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

"""Posttroll runner for the product-filtering"""
import logging
import os
import shutil
from urllib.parse import urlparse

from posttroll.publisher import Publish
from posttroll.subscriber import Subscribe

from .constants import AREA_CONFIG_PATH, METOP_LETTER, METOPS
from .definitions import (
    GranuleFilter,
    InconsistentMessage,
    NoValidTles,
    SceneNotSupported,
)

LOG = logging.getLogger(__name__)


def start_product_filtering(registry, message, options, **kwargs):
    """From a posttroll/trollstalker message start the pytroll product filtering"""

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
        granule_ok = GranuleFilter(options, area_def_file)(message)
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
    if granule_ok:
        LOG.info("Granule %s inside one area", str(registry[scene_id]))
        mletter = METOP_LETTER.get(platform_name)

        # Now do the copying of the file to disk changing the filename!
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

        if "sir_local_dir" in options:
            local_filepath = os.path.join(options["sir_local_dir"], filename)
            sir_filepath = os.path.join(options["sir_dir"], filename + "_original")
            shutil.copy(urlobj.path, local_filepath)
            LOG.info("File copied from %s to %s", urlobj.path, local_filepath)
            shutil.copy(local_filepath, sir_filepath)
            LOG.info("File copied from %s to %s", local_filepath, sir_filepath)

        if "destination" in options:
            dest_filepath = os.path.join(options["destination"], source_fname)
            if not os.path.exists(dest_filepath):
                shutil.copy(urlobj.path, dest_filepath)
                LOG.info("File copied from %s to %s", urlobj.path, dest_filepath)
            else:
                LOG.info(
                    "File is there (%s) already, don't copy...",
                    os.path.dirname(dest_filepath),
                )

        if "destination" not in options and "sir_local_dir" not in options:
            LOG.info("Don't do anything with this file...")

    else:
        LOG.info("Granule %s outside all areas", str(registry[scene_id]))

    return registry


def product_filter_live_runner(options):
    """Listens and triggers processing"""

    LOG.info("*** Start the (EUMETCast) Product-filter runner:")
    LOG.debug("Listens for messages of type: %s", str(options["message_types"]))
    with Subscribe("", options["message_types"], True) as subscr:
        with Publish("product_filter_runner", 0) as publisher:
            file_reg = {}
            for msg in subscr.recv():
                file_reg = start_product_filtering(
                    file_reg, msg, options, publisher=publisher
                )
                # Cleanup in file registry (keep only the last 5):
                keys = list(file_reg.keys())
                if len(keys) > 5:
                    keys.sort()
                    file_reg.pop(keys[0])
