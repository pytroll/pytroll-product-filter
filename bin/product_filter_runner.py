#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2017, 2018 Adam.Dybbroe

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
import yaml
import shutil
from glob import glob
from trollsift.parser import parse, globify, Parser

import logging
LOG = logging.getLogger(__name__)


AREA_CONFIG_PATH = os.environ.get('PYTROLL_CONFIG_DIR', './')

#: Default time format
_DEFAULT_TIME_FORMAT = '%Y-%m-%d %H:%M:%S'

#: Default log format
_DEFAULT_LOG_FORMAT = '[%(levelname)s: %(asctime)s : %(name)s] %(message)s'

import sys
from urlparse import urlparse
import posttroll.subscriber
from posttroll.publisher import Publish
from datetime import timedelta, datetime
from pyorbital.orbital import Orbital
from pyresample.spherical_geometry import point_inside, Coordinate
from pyresample import utils as pr_utils

METOPS = {'METOPA': 'Metop-A',
          'metopa': 'Metop-A',
          'METOPB': 'Metop-B',
          'metopb': 'Metop-B',
          'metopc': 'Metop-C',
          'METOPC': 'Metop-C'}

METOP_LETTER = {'Metop-A': 'a',
                'Metop-B': 'b',
                'Metop-C': 'c'}


def get_arguments():
    """
    Get command line arguments
    Return
    name of the service and the config filepath
    """
    import argparse

    parser = argparse.ArgumentParser()

    parser.add_argument('-c', '--config_file',
                        type=str,
                        dest='config_file',
                        default='',
                        help="The file containing " +
                        "configuration parameters e.g. product_filter_config.yaml")
    parser.add_argument("-s", "--service",
                        help="Name of the service (e.g. iasi-lvl2)",
                        dest="service",
                        type=str,
                        default="unknown")
    parser.add_argument("-e", "--environment",
                        help="The processing environment (utv/test/prod)",
                        dest="environment",
                        type=str,
                        default="unknown")
    parser.add_argument("-v", "--verbose",
                        help="print debug messages too",
                        action="store_true")

    args = parser.parse_args()

    if args.config_file == '':
        print "Configuration file required! product_filter_runner.py <file>"
        sys.exit()
    if args.environment == '':
        print "Environment required! Use command-line switch -s <service name>"
        sys.exit()
    if args.service == '':
        print "Service required! Use command-line switch -e <environment>"
        sys.exit()

    service = args.service.lower()
    environment = args.environment.lower()

    if 'template' in args.config_file:
        print "Template file given as master config, aborting!"
        sys.exit()

    return environment, service, args.config_file


def get_config(configfile, service, procenv):
    """Get the configuration from file"""

    with open(configfile, 'r') as fp_:
        config = yaml.load(fp_)

    options = {}
    for item in config:
        if not isinstance(config[item], dict):
            options[item] = config[item]
        elif item in [service]:
            for key in config[service]:
                if not isinstance(config[service][key], dict):
                    options[key] = config[service][key]
                elif key in [procenv]:
                    for memb in config[service][key]:
                        options[memb] = config[service][key][memb]

    return options


def granule_inside_area(start_time, end_time, platform_name, area_def, tle_file=None):
    """Check if a satellite data granule is over area interest, using the start and
    end times from the filename

    """

    try:
        metop = Orbital(platform_name, tle_file)
    except KeyError:
        LOG.exception(
            'Failed getting orbital data for {0}'.format(platform_name))
        LOG.critical(
            'Cannot determine orbit! Probably TLE file problems...\n' +
            'Granule will be set to be inside area of interest disregarding')
        return True

    corners = area_def.corners

    is_inside = False
    for dtobj in [start_time, end_time]:
        lon, lat, dummy = metop.get_lonlatalt(dtobj)
        point = Coordinate(lon, lat)
        if point_inside(point, corners):
            is_inside = True
            break

    return is_inside


def start_product_filtering(registry, message, options, **kwargs):
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

    if message.data['instruments'] in ['iasi', 'ascat']:
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

    if 'end_time' in message.data:
        end_time = message.data['end_time']
    else:
        LOG.warning("No end time in message!")
        if instrument in ['iasi']:
            end_time = start_time + timedelta(seconds=60 * 3)
        elif instrument in ['ascat']:
            end_time = start_time + timedelta(seconds=60 * 15)

    # Check that the input file really exists:
    if not os.path.exists(registry[scene_id]):
        LOG.error("File %s does not exist. Don't do anything...",
                  str(registry))
        return registry

    LOG.info("Sat and Instrument: " + platform_name + " " + instrument)

    # Now check if the area is within the area(s) of interest:

    tle_dirs = options['tle_dir']
    if not isinstance(tle_dirs, list):
        tle_dirs = [tle_dirs]
    tle_files = []
    for tledir in tle_dirs:
        tle_files = tle_files + glob(os.path.join(tledir, globify(options['tlefilename'])))

    tlep = Parser(options['tlefilename'])

    time_thr = timedelta(days=5)
    utcnow = datetime.utcnow()
    valid_tle_file = None
    for tlefile in tle_files:
        fname = os.path.basename(tlefile)
        res = tlep.parse(fname)
        dtobj = res['time']
        # try:
        #     dtobj=datetime.strptime(
        #         fname.split('tle-')[-1].split('.txt')[0], '%Y%m%d')
        # except ValueError:
        #     LOG.warning("Failed determine the date-time of the tle-file")
        #     valid_tle_file=tlefile
        #     break
        delta_t = abs(utcnow - dtobj)
        if delta_t < time_thr:
            time_thr = delta_t
            valid_tle_file = tlefile

    if not valid_tle_file:
        LOG.error("Failed finding a valid tle file!")
        return registry
    else:
        LOG.debug("Valid TLE file: %s", valid_tle_file)

    area_def_file = os.path.join(AREA_CONFIG_PATH, "areas.def")

    areaids = options['areas_of_interest']
    if not isinstance(areaids, list):
        areaids = [areaids]
    inside = False
    for areaid in areaids:
        area_def = pr_utils.load_area(area_def_file, areaid)
        inside = granule_inside_area(
            start_time, end_time, platform_name, area_def, valid_tle_file)
        if inside:
            break

    if inside:
        LOG.info("Granule %s inside one area", str(registry[scene_id]))

        mletter = METOP_LETTER.get(platform_name)

        # Now do the copying of the file to disk changing the filename!
        if instrument in ['iasi']:
            # Example: iasi_b__twt_l2p_1706211005.bin
            filename = 'iasi_{0}__twt_l2p_{1}.bin'.format(mletter,
                                                          start_time.strftime('%y%m%d%H%M'))
        elif instrument in ['ascat']:
            # Examples:
            # ascat_b_ears250_1706211008.bin
            # ascat_a_earscoa_1706211058.bin
            product_name = str(message.data['product'])[0:3]
            filename = 'ascat_{0}_ears{1}_{2}.bin'.format(mletter,
                                                          product_name,
                                                          start_time.strftime('%y%m%d%H%M'))

        local_filepath = os.path.join(options['sir_local_dir'], filename)
        sir_filepath = os.path.join(options['sir_dir'], filename + '_original')
        shutil.copy(urlobj.path, local_filepath)
        LOG.info("File copied from %s to %s", urlobj.path, local_filepath)
        shutil.copy(local_filepath, sir_filepath)
        LOG.info("File copied from %s to %s", local_filepath, sir_filepath)
    else:
        LOG.info("Granule %s outside all areas", str(registry[scene_id]))

    return registry


def product_filter_live_runner(options):
    """Listens and triggers processing"""

    LOG.info("*** Start the (EUMETCast) Product-filter runner:")
    LOG.debug("Listens for messages of type: %s", str(options['message_types']))
    with posttroll.subscriber.Subscribe('', options['message_types'], True) as subscr:
        with Publish('product_filter_runner', 0) as publisher:
            file_reg = {}
            for msg in subscr.recv():
                file_reg = start_product_filtering(
                    file_reg, msg, options, publisher=publisher)
                # Cleanup in file registry (keep only the last 5):
                keys = file_reg.keys()
                if len(keys) > 5:
                    keys.sort()
                    file_reg.pop(keys[0])


if __name__ == "__main__":
    from logging import handlers
    handler = logging.StreamHandler(sys.stderr)

    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(fmt=_DEFAULT_LOG_FORMAT,
                                  datefmt=_DEFAULT_TIME_FORMAT)

    handler.setFormatter(formatter)
    logging.getLogger('').addHandler(handler)
    logging.getLogger('').setLevel(logging.DEBUG)
    logging.getLogger('posttroll').setLevel(logging.INFO)

    (environ, service_name, config_filename) = get_arguments()
    OPTIONS = get_config(config_filename, service_name, environ)

    MAIL_HOST = 'localhost'
    SENDER = OPTIONS.get('mail_sender', 'safusr.u@smhi.se')
    MAIL_FROM = '"Orbital determination error" <' + str(SENDER) + '>'
    try:
        RECIPIENTS = OPTIONS.get("mail_subscribers").split()
    except AttributeError:
        RECIPIENTS = "adam.dybbroe@smhi.se"
    MAIL_TO = RECIPIENTS
    MAIL_SUBJECT = 'New Critical Event From product_filtering'

    smtp_handler = handlers.SMTPHandler(MAIL_HOST,
                                        MAIL_FROM,
                                        MAIL_TO,
                                        MAIL_SUBJECT)
    smtp_handler.setLevel(logging.CRITICAL)
    logging.getLogger('').addHandler(smtp_handler)

    LOG = logging.getLogger('product_filter_runner')

    product_filter_live_runner(OPTIONS)
