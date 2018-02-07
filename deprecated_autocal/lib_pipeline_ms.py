#!/usr/bin/python

import os, sys
import numpy as np
import pyrap.tables as tb

import logging
logger = logging.getLogger('PiLL')

class AllMss(object):

    def __init__(self, mss, s):
        """
        mss : list of MS filenames
        s : scheduler obj
        """
        self.s = s
        self.mss_list_str = sorted(mss)
        self.mss_list_obj = []
        for ms in sorted(mss):
            mss_list_obj.append(Ms(ms))

    def get_list_obj(self):
        return self.mss_list_obj

    def get_list_str(self):
        return self.mss_liat_str

    def get_str_wsclean(self):
        """
        Return a string with all mss names,
        useful for wsclean
        """
        return ' '.join(self.mss_liat_str)

    def run(self, cmd, log, cmd_type):
        for ms in self.mss_list_str:
            cmd = cmd.replace('$ms',ms)
            log = log.replace('$ms',ms)
            self.s.add(cmd, log, cmd_type)
        self.s.run(check=True)

    
class Ms(object):

    def __init__(self, filename):
        self.ms = filename


    def get_calname(self):
        """
        Check if MS is of a calibrator and return patch name
        """
        ra, dec = self.get_phase_centre()
        if abs(ra - 24.4220808) < 1  and abs(dec - 33.1597594) < 1: return '3C48'
        if abs(ra - 85.6505746) < 1  and abs(dec - 49.8520094) < 1: calname = '3C147'
        if abs(ra - 277.3824204) < 1  and abs(dec - 48.7461556) < 1: calname = '3C380'
        if abs(ra - 212.835495) < 1  and abs(dec - 52.202770) < 1: calname = '3C295'
        if abs(ra - 123.4001379) < 1  and abs(dec - 48.2173778) < 1: calname = '3C196'
        if abs(ra - 299.8681525) < 1  and abs(dec - 40.7339156) < 1: calname = 'CygA'
        logger.info("Calibrator found: %s." % calname)
        return calname


    def find_nchan(self):
        """
        Find number of channels
        """
        with tb.table(self.ms+'/SPECTRAL_WINDOW', ack=False) as t:
            nchan = t.getcol('NUM_CHAN')
        assert (nchan[0] == nchan).all() # all spw have same channels?
        logger.debug('%s: Number of channels: %i' (self.ms, nchan[0]))
        return nchan[0]
    
    
    def find_chanband(self):
        """
        Find bandwidth of a channel in Hz
        """
        with tb.table(self.ms+'/SPECTRAL_WINDOW', ack=False) as t:
            chan_w = t.getcol('CHAN_WIDTH')[0]
        assert all(x==chan_w[0] for x in chan_w) # all chans have same width
        logger.debug('%s: Chan-width: %f MHz' (self.ms, chan_w[0]/1.e6))
        return chan_w[0]
    
    
    def find_timeint(self):
        """
        Get time interval in seconds
        """
        with tb.table(self.ms, ack=False) as t:
            Ntimes = len(set(t.getcol('TIME')))
        with tb.table(self.ms+'/OBSERVATION', ack=False) as t:
            deltat = (t.getcol('TIME_RANGE')[0][1]-t.getcol('TIME_RANGE')[0][0])/Ntimes
        logger.debug('%s: Time interval: %f s' (self.ms, deltat))
        return deltat
    
    
    def get_phase_centre(self):
        """
        Get the phase centre of the first source (is it a problem?) of an MS
        values in deg
        """
        field_no = 0
        ant_no = 0
        with tb.table(self.ms + '/FIELD', ack=False) as field_table:
            direction = field_table.getcol('PHASE_DIR')
            ra = direction[ ant_no, field_no, 0 ]
            dec = direction[ ant_no, field_no, 1 ]
        logger.debug('%s: Phase centre: %f deg - %f deg' (self.ms, ra*180/np.pi, dec*180/np.pi))
        if ra < 0: ra += 2*np.pi
        return (ra*180/np.pi, dec*180/np.pi)


def find_nchan(ms):
    """
    Find number of channel in this ms
    """
    with tb.table(ms+'/SPECTRAL_WINDOW', ack=False) as t:
        nchan = t.getcol('NUM_CHAN')
    assert (nchan[0] == nchan).all() # all spw have same channels?
    logger.debug('Channel in '+ms+': '+str(nchan[0]))
    return nchan[0]


def find_chanband(ms):
    """
    Find bandwidth of a channel
    """
    with tb.table(ms+'/SPECTRAL_WINDOW', ack=False) as t:
        chan_w = t.getcol('CHAN_WIDTH')[0]
    assert all(x==chan_w[0] for x in chan_w) # all chans have same width
    logger.debug('Channel width in '+ms+': '+str(chan_w[0]/1e6)+' MHz')
    return chan_w[0]


def find_timeint(ms):
    """
    Get time interval in seconds
    """
    with tb.table(ms, ack=False) as t:
        Ntimes = len(set(t.getcol('TIME')))
    with tb.table(ms+'/OBSERVATION', ack=False) as t:
        deltat = (t.getcol('TIME_RANGE')[0][1]-t.getcol('TIME_RANGE')[0][0])/Ntimes
    logger.debug('Time interval for '+ms+': '+str(deltat))
    return deltat


def get_phase_centre(ms):
    """
    Get the phase centre of the first source (is it a problem?) of an MS
    values in deg
    """
    field_no = 0
    ant_no = 0
    with tb.table(ms + '/FIELD', ack=False) as field_table:
        direction = field_table.getcol('PHASE_DIR')
        ra = direction[ ant_no, field_no, 0 ]
        dec = direction[ ant_no, field_no, 1 ]
    return (ra*180/np.pi, dec*180/np.pi)

