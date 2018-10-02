#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 - Francesco de Gasperin
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

# Usage: BLavg.py vis.MS
# Load a MS, average visibilities according to the baseline lenght,
# i.e. shorter BLs are averaged more, and write a new MS

import os, sys
import optparse, itertools
import logging
import numpy as np
from scipy.ndimage.filters import gaussian_filter1d as gfilter
import pyrap.tables as pt
logging.basicConfig(level=logging.DEBUG)

def addcol(ms, incol, outcol):
    if outcol not in ms.colnames():
        logging.info('Adding column: '+outcol)
        coldmi = ms.getdminfo(incol)
        coldmi['NAME'] = outcol
        ms.addcols(pt.makecoldesc(outcol, ms.getcoldesc(incol)), coldmi)
    if outcol != incol:
        # copy columns val
        logging.info('Set '+outcol+'='+incol)
        pt.taql("update $ms set "+outcol+"="+incol)

opt = optparse.OptionParser(usage="%prog [options] MS", version="%prog 0.1")
opt.add_option('-f', '--ionfactor', help='Gives an indication on how strong is the ionosphere [default: 0.2]', type='float', default=0.2)
opt.add_option('-s', '--bscalefactor', help='Gives an indication on how the smoothing varies with BL-lenght [default: 0.5]', type='float', default=0.5)
opt.add_option('-i', '--incol', help='Column name to smooth [default: DATA]', type='string', default='DATA')
opt.add_option('-o', '--outcol', help='Output column [default: SMOOTHED_DATA]', type="string", default='SMOOTHED_DATA')
opt.add_option('-w', '--weight', help='Save the newly computed WEIGHT_SPECTRUM, this action permanently modify the MS! [default: False]', action="store_true", default=False)
opt.add_option('-r', '--restore', help='If WEIGHT_SPECTRUM_ORIG exists then restore it before smoothing [default: False]', action="store_true", default=False)
opt.add_option('-b', '--nobackup', help='Do not backup the old WEIGHT_SPECTRUM in WEIGHT_SPECTRUM_ORIG [default: do backup if -w]', action="store_true", default=False)
opt.add_option('-a', '--onlyamp', help='Smooth only amplitudes [default: smooth real/imag]', action="store_true", default=False)
(options, msfile) = opt.parse_args()

if msfile == []:
    opt.print_help()
    sys.exit(0)
msfile = msfile[0]

if not os.path.exists(msfile):
    logging.error("Cannot find MS file.")
    sys.exit(1)

# open input/output MS
ms = pt.table(msfile, readonly=False, ack=False)
        
freqtab = pt.table(msfile + '/SPECTRAL_WINDOW', ack=False)
freq = freqtab.getcol('REF_FREQUENCY')
freqtab.close()
wav = 299792458. / freq
timepersample = ms.getcell('INTERVAL',0)

# check if ms is time-ordered
times = ms.getcol('TIME_CENTROID')
if not all(times[i] <= times[i+1] for i in xrange(len(times)-1)):
    logging.critical('This code cannot handle MS that are not time-sorted.')
    sys.exit(1)

# create column to smooth
addcol(ms, options.incol, options.outcol)

# retore WEIGHT_SPECTRUM
if 'WEIGHT_SPECTRUM_ORIG' in ms.colnames() and options.restore:
    addcol(ms, 'WEIGHT_SPECTRUM_ORIG', 'WEIGHT_SPECTRUM')
# backup WEIGHT_SPECTRUM
elif options.weight and not options.nobackup:
    addcol(ms, 'WEIGHT_SPECTRUM', 'WEIGHT_SPECTRUM_ORIG')

# iteration on baseline combination
for ms_bl in ms.iter(["ANTENNA1","ANTENNA2"]):
    uvw = ms_bl.getcol('UVW')
    ant1 = ms_bl.getcol('ANTENNA1')[0]
    ant2 = ms_bl.getcol('ANTENNA2')[0]

    # compute the FWHM
    uvw_dist = np.sqrt(uvw[:, 0]**2 + uvw[:, 1]**2 + uvw[:, 2]**2)
    dist = np.mean(uvw_dist) / 1.e3
    if np.isnan(dist) or dist == 0: continue # fix for missing anstennas and autocorr
    
    stddev = options.ionfactor * (25.e3 / dist)**options.bscalefactor * (freq / 60.e6) # in sec
    stddev = stddev/timepersample # in samples
    logging.debug("%s - %s: dist = %.1f km: sigma=%.2f samples." % (ant1, ant2, dist, stddev))

    if stddev == 0: continue # fix for missing anstennas
    if stddev < 0.5: continue # avoid very small smoothing

    #logging.debug('Reading data')
    data = ms_bl.getcol(options.outcol)
    #logging.debug('Reading weights')
    weights = ms_bl.getcol('WEIGHT_SPECTRUM')
    #logging.debug('Reading flag')
    flags = ms_bl.getcol('FLAG')

    flags[ np.isnan(data) ] = True # flag NaNs
    weights[flags] = 0 # set weight of flagged data to 0
    del flags
    
    #logging.info('Smoothing baseline')
    
    # Multiply every element of the data by the weights, convolve both the scaled data and the weights, and then
    # divide the convolved data by the convolved weights (translating flagged data into weight=0). That's basically the equivalent of a
    # running weighted average with a Gaussian window function.
    
    # set bad data to 0 so nans do not propagate
    data = np.nan_to_num(data*weights)
    
    # smear weighted data and weights
    if options.onlyamp:
        dataAMP = gfilter(np.abs(data), stddev, axis=0)
        dataPH = np.angle(data)
    else:
        dataR = gfilter(np.real(data), stddev, axis=0)#, truncate=4.)
        dataI = gfilter(np.imag(data), stddev, axis=0)#, truncate=4.)

    weights = gfilter(weights, stddev, axis=0)#, truncate=4.)

    # re-create data
    if options.onlyamp:
        data = dataAMP * ( np.cos(dataPH) + 1j*np.sin(dataPH) )
    else:
        data = (dataR + 1j * dataI)
    data[(weights != 0)] /= weights[(weights != 0)] # avoid divbyzero

    #print np.count_nonzero(data[~flags]), np.count_nonzero(data[flags]), 100*np.count_nonzero(data[flags])/np.count_nonzero(data)
    #print "NANs in flagged data: ", np.count_nonzero(np.isnan(data[flags]))
    #print "NANs in unflagged data: ", np.count_nonzero(np.isnan(data[~flags]))
    #print "NANs in weights: ", np.count_nonzero(np.isnan(weights))

    #logging.info('Writing %s column.' % options.outcol)
    ms_bl.putcol(options.outcol, data)

    if options.weight:
        #logging.warning('Writing WEIGHT_SPECTRUM column.')
        ms_bl.putcol('WEIGHT_SPECTRUM', weights)

ms.close()
logging.info("Done.")
