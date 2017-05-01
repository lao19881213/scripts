#!/usr/bin/python
# perform self-calibration on a group of SBs concatenated in TCs. Script must be run in dir with MS.
# number/chan in MS are flexible but the must be concatenable (same chans/freq!)
# Input:
# TCs are blocks of SBs should have calibrator corrected (a+p) data in DATA (beam not applied).
# file format of TCs is: group#_TC###.MS.
# Output:
# TCs with selfcal corrected source subtracted data in CORRECTED_DATA
# instrument tables contain gain (slow) + fast (scalarphase+TEC) solutions
# last high/low resolution models are copied in the "self/models" dir
# last high/low resolution images + masks + empty images (CORRECTED_DATA) are copied in the "self/images" dir
# h5parm solutions and plots are copied in the "self/solutions" dir

import sys, os, glob, re
import numpy as np
from autocal.lib_pipeline import *
import pyrap.tables as pt
from make_mask import make_mask

parset_dir = '/home/fdg/scripts/autocal/parset_self/'
skymodel = '/home/fdg/scripts/model/calib-simple.skymodel'
niter = 3
user_mask = None

if 'tooth' in os.getcwd():
    sourcedb = '/home/fdg/scripts/autocal/LBAsurvey/toothbrush.LBA.skydb'
    apparent = True # no beam correction
    user_mask = '/home/fdg/scripts/autocal/regions/tooth.reg'
elif 'bootes' in os.getcwd():
    sourcedb = '/home/fdg/scripts/model/Bootes_HBA.corr.skydb'
    apparent = False
else:
    # Survey
    sourcedb = '/home/fdg/scripts/autocal/LBAsurvey/skymodels/%s_%s.skydb' % (os.getcwd().split('/')[-2], os.getcwd().split('/')[-1])
    apparent = False

#############################################################################

def ft_model_wsclean(ms, imagename, c, user_mask = None, resamp = None, keep_in_beam=True):
    """
    ms : string or vector of mss
    imagename : root name for wsclean model images
    resamp : must be '10asec' or another pixels size to resample models
    keep_in_beam : if True remove everything outside primary beam, otherwise everything inside
    """
    logger.info('Predict with model image...')

    # remove CC not in mask
    maskname = imagename+'-mask.fits'
    make_mask(image_name = imagename+'-MFS-image.fits', mask_name = maskname, threshisl = 5, atrous_do=True)
    if user_mask is not None: 
        blank_image_reg(maskname, user_mask, inverse=False, blankval=1)
    blank_image_reg(maskname, 'self/beam.reg', inverse=keep_in_beam)
    for modelname in sorted(glob.glob(imagename+'*model.fits')):
        blank_image_fits(modelname, maskname, inverse=True)

    if resamp is not None:
        for model in sorted(glob.glob(imagename+'*model.fits')):
            model_out = model.replace(imagename, imagename+'-resamp')
            s.add('~/opt/src/nnradd/build/nnradd '+resamp+' '+model_out+' '+model, log='resamp-c'+str(c)+'.log', log_append=True, cmd_type='general')
        s.run(check=True)
        imagename = imagename+'-resamp'
 
    if ms is list: ms = ' '.join(ms) # convert to string for wsclean
    s.add('wsclean -predict -name ' + imagename + ' -mem 90 -j '+str(s.max_processors)+' -channelsout 10 '+ms, \
            log='wscleanPRE-c'+str(c)+'.log', cmd_type='wsclean', processors='max')
    s.run(check=True)


def ft_model_cc(ms, imagename, c, user_mask = None, keep_in_beam=True):
    """
    skymodel : cc-list made by wsclean
    keep_in_beam : if True remove everything outside primary beam, otherwise everything inside
    """
    import lsmtool
    logger.info('Predict with CC...')
    maskname = imagename+'-mask.fits'
    skymodel = imagename+'-sources.txt'
    skydb = imagename+'-sources.skydb'

    # prepare mask
    if not os.path.exists(maskname):
        make_mask(image_name = imagename+'-MFS-image.fits', mask_name = maskname, threshisl = 5, atrous_do=True)
    if user_mask is not None:
        blank_image_reg(maskname, user_mask, inverse=False, blankval=1) # set to 1 pixels into user_mask
    blank_image_reg(maskname, 'self/beam.reg', inverse=keep_in_beam, blankval=0) # if keep_in_beam set to 0 everything outside beam.reg
    
    # apply mask
    lsm = lsmtool.load(skymodel)
    lsm.remove('%s == True' % maskname)
    lsm.write(skymodel, format='makesourcedb', clobber=True)
    del lsm

    # convert to skydb
    s.add('run_env.sh makesourcedb outtype="blob" format="<" in="'+skymodel+'" out="'+skydb+'"', log='makesourcedb-c'+str(c)+'.log', cmd_type='general')
    s.run(check=True)

    # predict
    for ms in mss:
        s.add('run_env.sh NDPPP '+parset_dir+'/NDPPP-predict.parset msin='+ms+' pre.usebeammodel=false pre.sourcedb='+skydb, log=ms+'_pre-c'+str(c)+'.log', cmd_type='NDPPP')
    s.run(check=True)


#############################################################################

logger = set_logger('pipeline-self.logger')
check_rm('logs')
s = Scheduler(dry=False)

##################################################
# Clear
#logger.info('Cleaning...')
#
#check_rm('img')
#os.makedirs('img')
os.makedirs('logs/mss')
#
## here images, models, solutions for each group will be saved
#check_rm('self')
#if not os.path.exists('self/images'): os.makedirs('self/images')
#if not os.path.exists('self/solutions'): os.makedirs('self/solutions')

mss = sorted(glob.glob('mss/TC*[0-9].MS'))
concat_ms = 'mss/concat.MS'

# make beam
phasecentre = get_phase_centre(mss[0])
make_beam_reg(phasecentre[0], phasecentre[1], 8, 'self/beam.reg') # go to 7 deg, first null

################################################################################################
## Create columns (non compressed)
## TODO: remove when moving to NDPPP DFT
#logger.info('Creating MODEL_DATA_HIGHRES and SUBTRACTED_DATA...')
#for ms in mss:
#    s.add('addcol2ms.py -m '+ms+' -c MODEL_DATA_HIGHRES,SUBTRACTED_DATA', log=ms+'_addcol.log', cmd_type='python')
#s.run(check=True)
#
####################################################################################################
## Add model to MODEL_DATA
## copy sourcedb into each MS to prevent concurrent access from multiprocessing to the sourcedb
#sourcedb_basename = sourcedb.split('/')[-1]
#for ms in mss:
#    check_rm(ms+'/'+sourcedb_basename)
#    logger.debug('Copy: '+sourcedb+' -> '+ms)
#    os.system('cp -r '+sourcedb+' '+ms)
#logger.info('Add model to MODEL_DATA...')
#for ms in mss:
#    if apparent:
#        s.add('NDPPP '+parset_dir+'/NDPPP-predict.parset msin='+ms+' pre.usebeammodel=false pre.sourcedb='+ms+'/'+sourcedb_basename, log=ms+'_pre.log', cmd_type='NDPPP')
#    else:
#        s.add('NDPPP '+parset_dir+'/NDPPP-predict.parset msin='+ms+' pre.usebeammodel=true pre.sourcedb='+ms+'/'+sourcedb_basename, log=ms+'_pre.log', cmd_type='NDPPP')
#s.run(check=True)
#
####################################################################################
## Preapre fake FR parmdb
#logger.info('Prepare fake FR parmdb...')
#for ms in mss:
#    if os.path.exists(ms+'/instrument-fr'): continue
#    s.add('calibrate-stand-alone -f --parmdb-name instrument-fr '+ms+' '+parset_dir+'/bbs-fakeparmdb-fr.parset '+skymodel, log=ms+'_fakeparmdb-fr.log', cmd_type='BBS')
#s.run(check=True)
#for ms in mss:
#    s.add('taql "update '+ms+'/instrument-fr::NAMES set NAME=substr(NAME,0,24)"', log=ms+'_taql.log', cmd_type='general')
#s.run(check=True)

#####################################################################################################
# Self-cal cycle
for c in xrange(niter):
    logger.info('Start selfcal cycle: '+str(c))

#    # Smooth DATA -> SMOOTHED_DATA
#    # Re-done in case of new flags
#    # TEST: higher ionfactor
#    if c == 0:
#        incol = 'DATA'
#    else:
#        incol = 'SUBTRACTED_DATA'
#
#    logger.info('BL-based smoothing...')
#    for ms in mss:
#        s.add('BLsmooth.py -r -f 0.2 -i '+incol+' -o SMOOTHED_DATA '+ms, log=ms+'_smooth1-c'+str(c)+'.log', cmd_type='python')
#    s.run(check=True)
#
#    logger.info('Concatenating TCs...')
#    check_rm(concat_ms+'*')
#    pt.msutil.msconcat(mss, concat_ms, concatTime=False)
#
#    # solve TEC - group*_TC.MS:SMOOTHED_DATA
#    logger.info('Solving TEC...')
#    for ms in mss:
#        check_rm(ms+'/instrument-tec')
#        s.add('NDPPP '+parset_dir+'/NDPPP-solTEC.parset msin='+ms+' sol.parmdb='+ms+'/instrument-tec', \
#                log=ms+'_solTEC-c'+str(c)+'.log', cmd_type='NDPPP')
#    s.run(check=True)
#
#    # LoSoTo plot
#    run_losoto(s, 'tec'+str(c), mss, [parset_dir+'/losoto-plot.parset'], ininstrument='instrument-tec', putback=False)
#    os.system('mv plots-tec'+str(c)+' self/solutions')
#    os.system('mv cal-tec'+str(c)+'.h5 self/solutions/')
#
#    # correct TEC - group*_TC.MS:(SUBTRACTED_)DATA -> group*_TC.MS:CORRECTED_DATA
#    logger.info('Correcting TEC...')
#    for ms in mss:
#        s.add('NDPPP '+parset_dir+'/NDPPP-corTEC.parset msin='+ms+' msin.datacolumn='+incol+' cor1.parmdb='+ms+'/instrument-tec cor2.parmdb='+ms+'/instrument-tec', \
#                log=ms+'_corTEC-c'+str(c)+'.log', cmd_type='NDPPP')
#    s.run(check=True)
#
#    #####################################################################################################
#    # Cross-delay + Faraday rotation correction
#    if c >= 1:
#
#        # To circular - SB.MS:CORRECTED_DATA -> SB.MS:CORRECTED_DATA (circular)
#        # TODO: check -w, is it ok?
#        logger.info('Convert to circular...')
#        for ms in mss:
#            s.add('/home/fdg/scripts/mslin2circ.py -w -i '+ms+':CORRECTED_DATA -o '+ms+':CORRECTED_DATA', log=ms+'_circ2lin-c'+str(c)+'.log', cmd_type='python')
#        s.run(check=True)
# 
#        # Smooth CORRECTED_DATA -> SMOOTHED_DATA
#        logger.info('BL-based smoothing...')
#        for ms in mss:
#            s.add('BLsmooth.py -r -f 0.5 -i CORRECTED_DATA -o SMOOTHED_DATA '+ms, log=ms+'_smooth2-c'+str(c)+'.log', cmd_type='python')
#        s.run(check=True)
#
#        # Solve G SB.MS:SMOOTHED_DATA (only solve)
#        logger.info('Solving G...')
#        for ms in mss:
#            check_rm(ms+'/instrument-g')
#            s.add('NDPPP '+parset_dir+'/NDPPP-solG.parset msin='+ms+' sol.parmdb='+ms+'/instrument-g sol.solint=30 sol.nchan=8', \
#                    log=ms+'_sol-g1-c'+str(c)+'.log', cmd_type='NDPPP')
#        s.run(check=True)
#
#        run_losoto(s, 'fr'+str(c), mss, [parset_dir+'/losoto-fr.parset'], ininstrument='instrument-g', inglobaldb='globaldb',
#            outinstrument='instrument-fr', outglobaldb='globaldb-fr', outtab='rotationmeasure000', putback=True)
#        os.system('mv plots-fr'+str(c)+' self/solutions/')
#        os.system('mv cal-fr'+str(c)+'.h5 self/solutions/')
#       
#        # To linear - SB.MS:CORRECTED_DATA -> SB.MS:CORRECTED_DATA (linear)
#        logger.info('Convert to linear...')
#        for ms in mss:
#            s.add('/home/fdg/scripts/mslin2circ.py -w -r -i '+ms+':CORRECTED_DATA -o '+ms+':CORRECTED_DATA', log=ms+'_circ2lin-c'+str(c)+'.log', cmd_type='python')
#        s.run(check=True)
#        
#        # Correct FR SB.MS:CORRECTED_DATA->CORRECTED_DATA
#        logger.info('Faraday rotation correction...')
#        for ms in mss:
#            s.add('NDPPP '+parset_dir+'/NDPPP-cor.parset msin='+ms+' cor.parmdb='+ms+'/instrument-fr cor.correction=RotationMeasure', log=ms+'_corFR-c'+str(c)+'.log', cmd_type='NDPPP')
#        s.run(check=True)
#
#        # Smooth CORRECTED_DATA -> SMOOTHED_DATA
#        logger.info('BL-based smoothing...')
#        for ms in mss:
#            s.add('BLsmooth.py -r -f 0.5 -i CORRECTED_DATA -o SMOOTHED_DATA '+ms, log=ms+'_smooth3-c'+str(c)+'.log', cmd_type='python')
#        s.run(check=True)
#
#        # Solve G SB.MS:SMOOTHED_DATA (only solve)
#        logger.info('Solving G...')
#        for ms in mss:
#            check_rm(ms+'/instrument-g')
#            s.add('NDPPP '+parset_dir+'/NDPPP-solG.parset msin='+ms+' sol.parmdb='+ms+'/instrument-g sol.solint=30 sol.nchan=8', \
#                    log=ms+'_sol-g2-c'+str(c)+'.log', cmd_type='NDPPP')
#        s.run(check=True)
#
#        run_losoto(s, 'cd'+str(c), mss, [parset_dir+'/losoto-cd.parset'], ininstrument='instrument-g', inglobaldb='globaldb',
#            outinstrument='instrument-cd', outglobaldb='globaldb', outtab='amplitude000,crossdelay', putback=True)
#        os.system('mv plots-cd'+str(c)+' self/solutions/')
#        os.system('mv cal-cd'+(str(c))+'.h5 self/solutions/')
#
#        #run_losoto(s, 'amp', mss, [parset_dir+'/losoto-amp.parset'], ininstrument='instrument-g', inglobaldb='globaldb',
#        #    outinstrument='instrument-amp', outglobaldb='globaldb', outtab='amplitude000,phase000', putback=True)
#        #os.system('mv plots-amp self/solutions/')
#        #os.system('mv cal-amp.h5 self/solutions/')
#
#        # Correct FR SB.MS:SUBTRACTED_DATA->CORRECTED_DATA
#        logger.info('Faraday rotation correction...')
#        for ms in mss:
#            s.add('NDPPP '+parset_dir+'/NDPPP-cor.parset msin='+ms+' msin.datacolumn=SUBTRACTED_DATA cor.parmdb='+ms+'/instrument-fr cor.correction=RotationMeasure', \
#                    log=ms+'_corFR-c'+str(c)+'.log', cmd_type='NDPPP')
#        s.run(check=True)
#       # Correct FR SB.MS:CORRECTED_DATA->CORRECTED_DATA
#        logger.info('Cross-delay correction...')
#        for ms in mss:
#            s.add('NDPPP '+parset_dir+'/NDPPP-cor.parset msin='+ms+' msin.datacolumn=CORRECTED_DATA cor.parmdb='+ms+'/instrument-cd cor.correction=Gain', log=ms+'_corCD-c'+str(c)+'.log', cmd_type='NDPPP')
#        s.run(check=True)
#        # Correct slow AMP SB.MS:CORRECTED_DATA->CORRECTED_DATA
#        #logger.info('Slow amp correction...')
#        #for ms in mss:
#        #    s.add('NDPPP '+parset_dir+'/NDPPP-cor.parset msin='+ms+' cor.parmdb='+ms+'/instrument-amp cor.correction=Gain', log=ms+'_corAMP-c'+str(c)+'.log', cmd_type='NDPPP')
#        #s.run(check=True)
#
#        # Finally re-calculate TEC
#        logger.info('BL-based smoothing...')
#        for ms in mss:
#            s.add('BLsmooth.py -r -f 0.2 -i CORRECTED_DATA -o SMOOTHED_DATA '+ms, log=ms+'_smooth3-c'+str(c)+'.log', cmd_type='python')
#        s.run(check=True)
#
#        # solve TEC - group*_TC.MS:SMOOTHED_DATA
#        logger.info('Solving TEC...')
#        for ms in mss:
#            check_rm(ms+'/instrument-tec')
#            s.add('NDPPP '+parset_dir+'/NDPPP-solTEC.parset msin='+ms+' sol.parmdb='+ms+'/instrument-tec', \
#                    log=ms+'_solTEC-c'+str(c)+'.log', cmd_type='NDPPP')
#        s.run(check=True)
#
#        # LoSoTo plot
#        run_losoto(s, 'tec'+str(c)+'b', mss, [parset_dir+'/losoto-plot.parset'], ininstrument='instrument-tec', putback=False)
#        os.system('mv plots-tec'+str(c)+'b self/solutions')
#        os.system('mv cal-tec'+str(c)+'b.h5 self/solutions')
#
#        # correct TEC - group*_TC.MS:CORRECTED_DATA -> group*_TC.MS:CORRECTED_DATA
#        logger.info('Correcting TEC...')
#        for ms in mss:
#            s.add('NDPPP '+parset_dir+'/NDPPP-corTEC.parset msin='+ms+' msin.datacolumn=CORRECTED_DATA cor1.parmdb='+ms+'/instrument-tec cor2.parmdb='+ms+'/instrument-tec', \
#                    log=ms+'_corTECb-c'+str(c)+'.log', cmd_type='NDPPP')
#        s.run(check=True)
#
#   ###################################################################################################################
#    # clen on concat.MS:CORRECTED_DATA (FR/TEC corrected, beam corrected)
#
#    # do beam-corrected+deeper image at last cycle
#    if c == niter-1:
#        # beam corrected: -use-differential-lofar-beam' - no baseline avg!
#        logger.info('Cleaning beam (cycle: '+str(c)+')...')
#        imagename = 'img/wideBeam'
#        s.add('wsclean -reorder -name ' + imagename + ' -size 4000 4000 -trim 3500 3500 -mem 90 -j '+str(s.max_processors)+' \
#                -scale 8arcsec -weight briggs 0.0 -auto-mask 10 -auto-threshold 1 -niter 100000 -no-update-model-required -mgain 0.8 \
#                -pol I -joinchannels -fit-spectral-pol 2 -channelsout 10 -apply-primary-beam -use-differential-lofar-beam '+' '.join(mss), \
#                log='wscleanBeam-c'+str(c)+'.log', cmd_type='wsclean', processors='max')
#        s.run(check=True)
#        # super low resolution to catch extended emission
#        logger.info('Cleaning beam-low (cycle: '+str(c)+')...')
#        imagename = 'img/wideBeamLow'
#        s.add('wsclean -reorder -name ' + imagename + ' -size 700 700 -trim 512 512 -mem 90 -j '+str(s.max_processors)+' \
#                -scale 1arcmin -weight briggs 0.0 -auto-mask 5 -auto-threshold 1 -niter 10000 -no-update-model-required -mgain 0.8 -maxuv-l 3000\
#                -pol I -joinchannels -fit-spectral-pol 2 -channelsout 10 -apply-primary-beam -use-differential-lofar-beam '+' '.join(mss), \
#                log='wscleanBeamLow-c'+str(c)+'.log', cmd_type='wsclean', processors='max')
#        s.run(check=True)
#
#    # clean mask clean (cut at 5k lambda)
#    # no MODEL_DATA update with -baseline-averaging
#    logger.info('Cleaning (cycle: '+str(c)+')...')
#    imagename = 'img/wide-'+str(c)
#    s.add('wsclean -reorder -name ' + imagename + ' -size 3000 3000 -trim 2500 2500 -mem 90 -j '+str(s.max_processors)+' -baseline-averaging 2.0 \
#            -scale 10arcsec -weight briggs 0.0 -niter 100000 -no-update-model-required -maxuv-l 5000 -mgain 0.9 \
#            -pol I -joinchannels -fit-spectral-pol 2 -channelsout 10 -auto-threshold 20 '+' '.join(mss), \
#            log='wsclean-c'+str(c)+'.log', cmd_type='wsclean', processors='max')
#    s.run(check=True)
#
#    maskname = imagename+'-mask.fits'
#    make_mask(image_name = imagename+'-MFS-image.fits', mask_name = maskname, threshisl = 3, atrous_do=True)
#    if user_mask is not None: 
#        blank_image_reg(maskname, user_mask, inverse=False, blankval=1)
#
#    logger.info('Cleaning w/ mask (cycle: '+str(c)+')...')
    imagename = 'img/widem-'+str(c) # TODO: change m->M
#    #-multiscale -multiscale-scale-bias 0.5 -multiscale-scales 0,9 \
#    s.add('run_envw.sh wsclean -reorder -name ' + imagename + ' -size 3000 3000 -trim 2500 2500 -mem 90 -j '+str(s.max_processors)+' -baseline-averaging 2.0 \
#            -scale 12arcsec -weight briggs 0.0 -niter 1000000 -no-update-model-required -maxuv-l 5000 -mgain 0.8 \
#            -pol I -joinchannels -fit-spectral-pol 2 -channelsout 10 -auto-threshold 0.1 -save-source-list -fitsmask '+maskname+' '+' '.join(mss), \
#            log='wscleanM-c'+str(c)+'.log', cmd_type='wsclean', processors='max')
#    s.run(check=True)
#    os.system('cat logs/wscleanM-c'+str(c)+'.log | grep Jy')

    #ft_model_wsclean(concat_ms, imagename, c, user_mask = user_mask)
    ft_model_cc(mss, imagename, c, user_mask = user_mask, keep_in_beam=True)
    sys.exit()

#    if c >= 1:
#        # TODO: TESTESTEST
#        s.add('wsclean -reorder -name ' + imagename + '-lr-test -size 5000 5000 -trim 4000 4000 -mem 90 -j '+str(s.max_processors)+' -baseline-averaging 2.0 \
#                -scale 20arcsec -weight briggs 0.0 -niter 100000 -no-update-model-required -maxuv-l 2000 -mgain 0.8 \
#                -pol I -joinchannels -fit-spectral-pol 2 -channelsout 10 -auto-threshold 1 '+' '.join(mss), \
#                log='wsclean-lr.log', cmd_type='wsclean', processors='max')
#        s.run(check=True)
#        # TODO: TESTTESTTEST correct TEC - group*_TC.MS:SUBTRACTED_DATA -> group*_TC.MS:CORRECTED_DATA
#        logger.info('Correcting TEC...')
#        for ms in mss:
#            s.add('NDPPP '+parset_dir+'/NDPPP-corTEC.parset msin='+ms+' msin.datacolumn=SUBTRACTED_DATA cor1.parmdb='+ms+'/instrument-tec cor2.parmdb='+ms+'/instrument-tec', \
#                log=ms+'_corTECb-c'+str(c)+'.log', cmd_type='NDPPP')
#        s.run(check=True)
#        s.add('wsclean -reorder -name ' + imagename + '-test -size 3500 3500 -trim 3000 3000 -mem 90 -j '+str(s.max_processors)+' -baseline-averaging 2.0 \
#            -scale 10arcsec -weight briggs 0.0 -niter 100000 -no-update-model-required -maxuv-l 6000 -mgain 0.8 \
#            -pol I -joinchannels -fit-spectral-pol 2 -channelsout 10 -auto-threshold 20 '+' '.join(mss), \
#            log='wscleanA-c'+str(c)+'.log', cmd_type='wsclean', processors='max')
#        s.run(check=True)

    # do low-res first cycle and remove it from the data
    if c == 0:
        # Subtract model from all TCs - concat.MS:CORRECTED_DATA - MODEL_DATA -> concat.MS:CORRECTED_DATA (selfcal corrected, beam corrected, high-res model subtracted)
        logger.info('Subtracting high-res model (CORRECTED_DATA = CORRECTED_DATA - MODEL_DATA)...')
        s.add('taql "update '+concat_ms+' set CORRECTED_DATA = CORRECTED_DATA - MODEL_DATA"', log='taql1-c'+str(c)+'.log', cmd_type='general')
        s.run(check=True)
    
        # reclean low-resolution
        logger.info('Cleaning low resolution...')
        imagename_lr = 'img/wide-lr'
        #-multiscale -multiscale-scale-bias 0.5 \
        s.add('run_envw.sh wsclean -reorder -name ' + imagename_lr + ' -size 4500 4500 -trim 4000 4000 -mem 90 -j '+str(s.max_processors)+' -baseline-averaging 2.0 \
                -scale 20arcsec -weight briggs 0.0 -niter 100000 -no-update-model-required -maxuv-l 2000 -mgain 0.8 \
                -pol I -joinchannels -fit-spectral-pol 2 -channelsout 10 -auto-threshold 1 -save-source-list '+' '.join(mss), \
                log='wsclean-lr.log', cmd_type='wsclean', processors='max')
        s.run(check=True)
       
        #ft_model_wsclean(concat_ms, imagename_lr+'-resamp', 'lr', user_mask=None, resamp='10asec', keep_in_beam=False)
        ft_model_cc(mss, imagename_lr, c, keep_in_beam=False)

        # corrupt model with TEC solutions ms:MODEL_DATA -> ms:MODEL_DATA
        for ms in mss:
            s.add('NDPPP '+parset_dir+'/NDPPP-corTEC.parset msin='+ms+' msin.datacolumn=MODEL_DATA msout.datacolumn=MODEL_DATA  \
                cor1.parmdb='+ms+'/instrument-tec cor1.invert=false cor2.parmdb='+ms+'/instrument-tec cor2.invert=false', \
                log=ms+'_corrupt.log', cmd_type='NDPPP')
        s.run(check=True)
    
        # Subtract low-res model - concat.MS:CORRECTED_DATA - MODEL_DATA -> concat.MS:CORRECTED_DATA (empty)
        logger.info('Subtracting low-res model (SUBTRACTED_DATA = DATA - MODEL_DATA)...')
        s.add('taql "update '+concat_ms+' set SUBTRACTED_DATA = DATA - MODEL_DATA"', log='taql2-c'+str(c)+'.log', cmd_type='general')
        s.run(check=True)

        # put in MODEL_DATA the best available model
        logger.info('Predict...')
        s.add('wsclean -predict -name ' + imagename + ' -mem 90 -j '+str(s.max_processors)+' -channelsout 10 '+concat_ms, \
                log='wscleanPRE2-c'+str(c)+'.log', cmd_type='wsclean', processors='max')
        s.run(check=True)

    ###############################################################################################################
    # Flag on residuals (CORRECTED_DATA)
    #logger.info('Flagging residuals...')
    #for ms in mss:
    #    s.add('NDPPP '+parset_dir+'/NDPPP-flag.parset msin='+ms, log=ms+'_flag-c'+str(c)+'.log', cmd_type='NDPPP')
    #s.run(check=True
    
# Copy images
[ os.system('mv img/wideM-'+str(c)+'-MFS-image.fits self/images') for c in xrange(niter) ]
os.system('mv img/wide-lr-MFS-image.fits self/images')
os.system('mv img/wideBeam-MFS-image.fits img/wideBeam-MFS-image-pb.fits self/images')
os.system('mv img/wideBeamLow-MFS-image.fits img/wideBeamLow-MFS-image-pb.fits self/images')
os.system('mv img/wideM-'+str(niter-1)+'-sources.txt self/skymodel.txt')
os.system('mv logs self')

logger.info("Done.")
