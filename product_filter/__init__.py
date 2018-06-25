#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2017, 2018 Adam.Dybbroe

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

from pyorbital.orbital import Orbital
from trollsched.satpass import Pass
#from pyresample.spherical_geometry import point_inside, Coordinate
import logging
LOG = logging.getLogger(__name__)


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

    tle1 = metop.tle.line1
    tle2 = metop.tle.line2

    mypass = Pass(platform_name, start_time, end_time, None, None, instrument='ascat',
                  tle1=tle1, tle2=tle2, frequency=500)
    acov = mypass.area_coverage(area_def)
    LOG.debug("Granule coverage of area: %f", acov)

    return (acov > 0.10)

    # is_inside = False
    # corners = area_def.corners
    # for dtobj in [start_time, end_time]:
    #     lon, lat, dummy = metop.get_lonlatalt(dtobj)
    #     point = Coordinate(lon, lat)
    #     if point_inside(point, corners):
    #         is_inside = True
    #         break
    # return is_inside
