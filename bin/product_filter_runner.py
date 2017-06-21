#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2017 Adam.Dybbroe

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

"""Posttroll runner for the product-filtering
"""

import os
import ConfigParser
import shutil
from glob import glob

import logging
LOG = logging.getLogger(__name__)

CONFIG_PATH = os.environ.get('PRODUCT_FILTER_RUNNER_CONFIG_DIR', './')

CONF = ConfigParser.ConfigParser()
CONF.read(os.path.join(CONFIG_PATH, "product_filter_config.cfg"))

MODE = os.getenv("SMHI_MODE")
if MODE is None:
    MODE = "offline"

#: Default time format
_DEFAULT_TIME_FORMAT = '%Y-%m-%d %H:%M:%S'

#: Default log format
_DEFAULT_LOG_FORMAT = '[%(levelname)s: %(asctime)s : %(name)s] %(message)s'

OPTIONS = {}
for option, value in CONF.items(MODE, raw=True):
    OPTIONS[option] = value

SIR_DIR = OPTIONS['sir_dir']
try:
    SIR_LOCALDIR = OPTIONS['sir_local_dir']
except KeyError:
    SIR_LOCALDIR = None

OPTIONS.update({k: OPTIONS[k].split(",")
                for k in OPTIONS if "," in OPTIONS[k]})

TLEDIR = OPTIONS['tle_dir']
print("TLEDIR = {0}".format(TLEDIR))

AREA_IDS = OPTIONS['areas_of_interest']
AREA_DEF_FILE = os.path.join(CONFIG_PATH, "areas.def")

import sys
from urlparse import urlparse
import posttroll.subscriber
from posttroll.publisher import Publish
from datetime import timedelta, datetime
from pyorbital.orbital import Orbital
from pyresample.spherical_geometry import point_inside, Coordinate
from pyresample import utils as pr_utils

METOPS = {'METOPA': 'Metop-A', 'METOPB': 'Metop-B', 'METOPC': 'Metop-C'}
METOP_LETTER = {'Metop-A': 'a',
                'Metop-B': 'b',
                'Metop-C': 'c'}


def granule_inside_area(start_time, end_time, platform_name, area_def, tle_file=None):
    """Check if a satellite data granule is over area interest, using the start and
    end times from the filename

    """

    metop = Orbital(platform_name, tle_file)
    corners = area_def.corners

    is_inside = False
    for dtobj in [start_time, end_time]:
        lon, lat, dummy = metop.get_lonlatalt(dtobj)
        point = Coordinate(lon, lat)
        if point_inside(point, corners):
            is_inside = True
            break

    return is_inside


def start_product_filtering(registry, message, **kwargs):
    """From a posttroll/trollstalker message start the pytroll product filtering"""

    LOG.info("")
    LOG.info("registry dict: " + str(registry))
    LOG.info("\tMessage:")
    LOG.info(message)
    urlobj = urlparse(message.data['uri'])

    if 'start_time' in message.data:
        start_time = message.data['start_time']
        scene_id = start_time.strftime('%Y%m%d%H%M')
    else:
        LOG.warning("No start time in message!")
        start_time = None
        return registry

    if 'end_time' in message.data:
        end_time = message.data['end_time']
    else:
        LOG.warning("No end time in message!")
        end_time = start_time + timedelta(seconds=60 * 3)

    if message.data['instruments'] == 'iasi':

        path, fname = os.path.split(urlobj.path)
        LOG.debug("path " + str(path) + " filename = " + str(fname))

        instrument = str(message.data['instruments'])
        platform_name = METOPS.get(
            message.data['satellite'], message.data['satellite'])
        registry[scene_id] = os.path.join(path, fname)
    else:
        LOG.debug("Scene is not supported")
        LOG.debug("platform and instrument: " +
                  str(message.data['platform_name']) + " " +
                  str(message.data['instruments']))
        return registry

    # Check that the input file really exists:
    if not os.path.exists(registry[scene_id]):
        LOG.error("File %s does not exist. Don't do anything...",
                  str(registry))
        return registry

    LOG.info("Sat and Instrument: " + platform_name + " " + instrument)

    # Now check if the area is within the area(s) of interest:
    tle_dirs = TLEDIR
    if not isinstance(tle_dirs, list):
        tle_dirs = [tle_dirs]
    tle_files = []
    for tledir in tle_dirs:
        tle_files = tle_files + glob(os.path.join(tledir, 'tle-*.txt'))

    time_thr = timedelta(days=1)
    for tlefile in tle_files:
        fname = os.path.basename(tlefile)

    tlefile = tle_files[0]
    if not isinstance(AREA_IDS, list):
        AREA_IDS = [AREA_IDS]
    inside = False
    for areaid in AREA_IDS:
        area_def = pr_utils.load_area(AREA_DEF_FILE, areaid)
        inside = granule_inside_area(
            start_time, end_time, platform_name, area_def, tlefile)
        if inside:
            break

    if inside:
        LOG.info("Granule {0} inside one area".format(registry[scene_id]))
    else:
        LOG.info("Granule {0} outside all areas".format(registry[scene_id]))

    # Now do the copying of the file to disk changing the filename!
    # Example: iasi_b__twt_l2p_1706211005.bin
    mletter = METOP_LETTER.get(platform_name)
    filename = 'iasi_{0}__twt_l2p_{1}.bin'.format(mletter,
                                                  start_time.strftime('%y%m%d%H%M'))
    local_filepath = os.path.join(OPTIONS['sir_local_dir'], filename)
    shutil.copy(urlobj.path, local_filepath)
    sir_filepath = os.path.join(OPTIONS['sir_dir'], filename + '_original')
    shutil.copy(local_filepath, sir_filepath)

    return registry


def product_filter_live_runner():
    """Listens and triggers processing"""

    LOG.info("*** Start the (EUMETCast) Product-filter runner:")
    with posttroll.subscriber.Subscribe('', ['SOUNDING/IASI/L2/TWT', ], True) as subscr:
        with Publish('product_filter_runner', 0) as publisher:
            file_reg = {}
            for msg in subscr.recv():
                file_reg = start_product_filtering(
                    file_reg, msg, publisher=publisher)
                # Cleanup in file registry (keep only the last 5):
                keys = file_reg.keys()
                if len(keys) > 5:
                    keys.sort()
                    file_reg.pop(keys[0])


if __name__ == "__main__":

    handler = logging.StreamHandler(sys.stderr)

    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(fmt=_DEFAULT_LOG_FORMAT,
                                  datefmt=_DEFAULT_TIME_FORMAT)
    handler.setFormatter(formatter)
    logging.getLogger('').addHandler(handler)
    logging.getLogger('').setLevel(logging.DEBUG)
    logging.getLogger('posttroll').setLevel(logging.INFO)

    LOG = logging.getLogger('product_filter_runner')

    product_filter_live_runner()
