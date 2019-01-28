#!/usr/bin/env python
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

"""Posttroll runner for the product-filtering
"""

import sys
import os
import shutil
from urlparse import urlparse
import posttroll.subscriber
from posttroll.publisher import Publish
from product_filter import (get_config,
                            GranuleFilter)
from product_filter import (InconsistentMessage, NoValidTles, SceneNotSupported)

import logging
LOG = logging.getLogger(__name__)


AREA_CONFIG_PATH = os.environ.get('PYTROLL_CONFIG_DIR', './')

#: Default time format
_DEFAULT_TIME_FORMAT = '%Y-%m-%d %H:%M:%S'

#: Default log format
_DEFAULT_LOG_FORMAT = '[%(levelname)s: %(asctime)s : %(name)s] %(message)s'

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
    parser.add_argument("--nagios",
                        help="The nagios/monitoring config file path",
                        dest="nagios_file",
                        type=str,
                        default="")
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

    return environment, service, args.config_file, args.nagios_file


def start_product_filtering(registry, message, options, **kwargs):
    """From a posttroll/trollstalker message start the pytroll product filtering"""

    LOG.info("")
    LOG.info("registry dict: " + str(registry))
    LOG.info("\tMessage:")
    LOG.info(message)

    # Get yaml config:
    if options['nagios_config_file'] is not None:
        LOG.debug("Config file - nagios monitoring: %s", options['nagios_config_file'])
        LOG.debug("Environment: %s", options['environment'])
        hook_options = get_config(options['nagios_config_file'],
                                  'ascat_hook'+str(options['environment']), '')
    else:
        hook_options = {}

    urlobj = urlparse(message.data['uri'])

    start_time = message.data['start_time']
    scene_id = start_time.strftime('%Y%m%d%H%M')
    instrument = str(message.data['instruments'])
    platform_name = METOPS.get(
        message.data['satellite'], message.data['satellite'])
    source_path, source_fname = os.path.split(urlobj.path)

    area_def_file = os.path.join(AREA_CONFIG_PATH, "areas.def")
    try:
        granule_ok = GranuleFilter(options, area_def_file)(message)
        if instrument in ['ascat'] and 'ascat_hook' in hook_options:
            hook_options['ascat_hook'](0, "OK")
    except (InconsistentMessage, NoValidTles, SceneNotSupported, IOError) as e__:
        LOG.exception("Could not do the granule filtering...")
        if instrument in ['ascat'] and 'ascat_hook' in hook_options:
            hook_options['ascat_hook'](2, "ERROR: Could not do the granule filtering...")
        return registry

    registry[scene_id] = os.path.join(source_path, source_fname)

    if granule_ok:
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

        if 'sir_local_dir' in options:
            local_filepath = os.path.join(options['sir_local_dir'], filename)
            sir_filepath = os.path.join(options['sir_dir'], filename + '_original')
            shutil.copy(urlobj.path, local_filepath)
            LOG.info("File copied from %s to %s", urlobj.path, local_filepath)
            shutil.copy(local_filepath, sir_filepath)
            LOG.info("File copied from %s to %s", local_filepath, sir_filepath)

        if 'destination' in options:
            dest_filepath = os.path.join(options['destination'], source_fname)
            if not os.path.exists(dest_filepath):
                shutil.copy(urlobj.path, dest_filepath)
                LOG.info("File copied from %s to %s", urlobj.path, dest_filepath)
            else:
                if instrument in ['ascat'] and 'ascat_hook' in hook_options:
                    hook_options['ascat_hook'](
                        1, "WARNING: File is there (%s) already, don't copy..." % os.path.dirname(dest_filepath))
                LOG.info("File is there (%s) already, don't copy...", os.path.dirname(dest_filepath))

        if not 'destination' in options and not 'sir_local_dir' in options:
            LOG.info("Don't do anything with this file...")

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

    (environ, service_name, config_filename, nagios_config_file) = get_arguments()
    OPTIONS = get_config(config_filename, service_name, environ)
    OPTIONS['environment'] = environ
    OPTIONS['nagios_config_file'] = nagios_config_file
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
