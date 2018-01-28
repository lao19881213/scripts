#!/usr/bin/python
# demix of a set of SBs from a given dir, output is in the local dir

parset_dir = '/home/fdg/scripts/autocal/parset_demix/'
origmss_dir = './uv/'

###################################################

import sys, os, glob
import numpy as np
from autocal.lib_pipeline import *

logger = set_logger('pipeline-demix.logger')
check_rm('logs')
s = Scheduler(dry=False, max_threads = 4) # set here max number of threads here
mss = sorted(glob.glob(origmss_dir+'/*MS'))

##############################################
#TODO: add flag?
# Demix
logger.info('Demixing...')
for ms in mss:
    if os.path.exists(os.path.basename(ms)): continue
    s.add('NDPPP '+parset_dir+'/NDPPP_demix.parset msin='+ms+' msout='+os.path.basename(ms)+' demixer.instrumentmodel='+os.path.basename(ms)+'/instrument_demix', log=os.path.basename(ms)+'_demix.log', cmd_type='NDPPP', processors=6)
s.run(check=True)

logger.info("Done.")
