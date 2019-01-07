#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2017, 2018, 2019 Adam.Dybbroe

# Author(s):

#   Adam.Dybbroe <a000680@c20671.ad.smhi.se>

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

"""Package file for the product-filter
"""

import os
import yaml
from urlparse import urlparse
from pyorbital.orbital import Orbital
from datetime import timedelta, datetime
from trollsched.satpass import Pass
from trollsift.parser import globify, Parser
from pyresample import utils as pr_utils
from glob import glob

import logging
LOG = logging.getLogger(__name__)

METOPS = {'METOPA': 'Metop-A',
          'metopa': 'Metop-A',
          'METOPB': 'Metop-B',
          'metopb': 'Metop-B',
          'metopc': 'Metop-C',
          'METOPC': 'Metop-C'}


class InconsistentMessage(Exception):
    pass


class NoValidTles(Exception):
    pass


class SceneNotSupported(Exception):
    pass


class GranuleFilter(object):

    def __init__(self, config, area_def_file):

        self.area_def_file = area_def_file
        self.instrument = config['instrument']
        self.tle_dirs = config['tle_dir']
        self.tlefilename = config['tlefilename']
        self.areaids = config['areas_of_interest']
        self.min_coverage = config['min_coverage']
        self.passlength_seconds = config['passlength_seconds']
        self.save_coverage_plot = config.get('save_coverage_plot', False)

    def __call__(self, message):

        urlobj = urlparse(message.data['uri'])

        if 'start_time' in message.data:
            start_time = message.data['start_time']
        else:
            raise InconsistentMessage("No start time in message!")

        if message.data['instruments'] == self.instrument:
            path, fname = os.path.split(urlobj.path)
            LOG.debug("path " + str(path) + " filename = " + str(fname))
            instrument = str(message.data['instruments'])
            LOG.debug("Instrument %r supported!", instrument)
            platform_name = METOPS.get(
                message.data['satellite'], message.data['satellite'])
            filepath = os.path.join(path, fname)
        else:
            LOG.debug("Scene is not supported")
            raise SceneNotSupported("platform and instrument: " +
                                    str(message.data['platform_name']) + " " +
                                    str(message.data['instruments']))

        if 'end_time' in message.data:
            end_time = message.data['end_time']
        else:
            LOG.warning("No end time in message!")
            end_time = start_time + timedelta(seconds=self.passlength_seconds)
            LOG.info("End time set to: %s", str(end_time))

        # Check that the input file really exists:
        if not os.path.exists(filepath):
            #LOG.error("File %s does not exist. Don't do anything...", filepath)
            raise IOError("File %s does not exist. Don't do anything...", filepath)

        LOG.info("Sat and Instrument: " + platform_name + " " + instrument)

        if not isinstance(self.tle_dirs, list):
            tle_dirs = [self.tle_dirs]
        tle_files = []
        for tledir in tle_dirs:
            tle_files = tle_files + glob(os.path.join(tledir, globify(self.tlefilename)))

        tlep = Parser(self.tlefilename)

        time_thr = timedelta(days=5)
        utcnow = datetime.utcnow()
        valid_tle_file = None
        for tlefile in tle_files:
            fname = os.path.basename(tlefile)
            res = tlep.parse(fname)
            dtobj = res['time']

            delta_t = abs(utcnow - dtobj)
            if delta_t < time_thr:
                time_thr = delta_t
                valid_tle_file = tlefile

        if not valid_tle_file:
            raise NoValidTles("Failed finding a valid tle file!")
        else:
            LOG.debug("Valid TLE file: %s", valid_tle_file)

        if not isinstance(self.areaids, list):
            self.areaids = [self.areaids]
        inside = False
        for areaid in self.areaids:
            area_def = pr_utils.load_area(self.area_def_file, areaid)
            inside = self.granule_inside_area(start_time, end_time,
                                              platform_name,
                                              area_def,
                                              valid_tle_file)
            if inside:
                return True

        return False

    def granule_inside_area(self, start_time, end_time, platform_name,
                            area_def, tle_file=None):
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

        tle1 = metop.tle.line1
        tle2 = metop.tle.line2

        mypass = Pass(platform_name, start_time, end_time, instrument=self.instrument,
                      tle1=tle1, tle2=tle2)
        acov = mypass.area_coverage(area_def)
        LOG.debug("Granule coverage of area %s: %f", area_def.area_id, acov)

        is_inside = (acov > self.min_coverage)

        if is_inside and self.save_coverage_plot:
            from pyresample.boundary import AreaDefBoundary
            from trollsched.drawing import save_fig
            area_boundary = AreaDefBoundary(area_def, frequency=100)
            area_boundary = area_boundary.contour_poly
            save_fig(mypass, poly=area_boundary, directory='/tmp')

        return is_inside


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


def granule_inside_area(start_time, end_time, platform_name, instrument,
                        area_def, thr_area_coverage, tle_file=None):
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

    tle1 = metop.tle.line1
    tle2 = metop.tle.line2

    mypass = Pass(platform_name, start_time, end_time, instrument=instrument,
                  tle1=tle1, tle2=tle2)
    acov = mypass.area_coverage(area_def)
    LOG.debug("Granule coverage of area %s: %f", area_def.area_id, acov)

    is_inside = (acov > thr_area_coverage)

    if is_inside:
        from pyresample.boundary import AreaDefBoundary
        from trollsched.drawing import save_fig
        area_boundary = AreaDefBoundary(area_def, frequency=100)
        area_boundary = area_boundary.contour_poly
        save_fig(mypass, poly=area_boundary, directory='/tmp')

    return
