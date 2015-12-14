#!/usr/bin/python
# download from LTA using WGET

download_file = 'cyga1.txt'

###################################################

import sys, os, glob
import numpy as np
from lib_pipeline import *

set_logger()
check_rm('logs')
s = Scheduler(dry=False, max_threads = 4) # set here max number of threads here

df = open(download_file,'r')

logging.info('Downloading...')
for i, line in enumerate(df):
    logging.debung('Download: '+line)
    s.add('wget -nv '+line+'  -O - | tar -x', log=str(i)+'.log', cmd_type='general')
    print 'wget -nv '+line+'  -O - | tar -x'
s.run(check=True)

logging.info("Done.")
