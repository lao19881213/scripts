#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Parallelizator
# USAGE:
# def flag(funct_param, outQueue=None):
#     pass
#     outQueue.put([funct_output])
#
# # start processes for multi-thread
# mpm = multiprocManager(ncpu, funct)
# mpm.put([funct_params])
# mpm.wait()
# for r in mpm.get():
#     print "funct_output:", r

import sys
import logging
import multiprocessing


class multiprocManager(object):

    class multiThread(multiprocessing.Process):
        """
        This class is a working thread which load parameters from a queue and
        return in the output queue
        """

        def __init__(self, inQueue, outQueue, funct):
            multiprocessing.Process.__init__(self)
            self.inQueue = inQueue
            self.outQueue = outQueue
            self.funct = funct

        def run(self):

            while True:
                parms = self.inQueue.get()

                # poison pill
                if parms is None:
                    self.inQueue.task_done()
                    break

                self.funct(*parms, outQueue=self.outQueue)
                self.inQueue.task_done()


    def __init__(self, procs=1, funct=None):
        """
        Manager for multiprocessing
        procs: number of processors
        funct: function to parallelize / note that the last parameter of this function must be the outQueue
        and it will be linked to the output queue
        """
        self.procs = procs
        self._threads = []
        self.inQueue = multiprocessing.JoinableQueue()
        self.outQueue = multiprocessing.Queue()
        self.runs = 0
        
        logging.debug('Spawning %i threads...' % self.procs)
        for proc in xrange(self.procs):
            t = self.multiThread(self.inQueue, self.outQueue, funct)
            self._threads.append(t)
            t.start()

    def put(self, args):
        """
        Parameters to give to the next jobs sent into queue
        """
        self.inQueue.put(args)
        self.runs += 1

    def get(self):
        """
        Return all the results as an iterator
        """
        # NOTE: do not use queue.empty() check which is unreliable
        # https://docs.python.org/2/library/multiprocessing.html
        for run in xrange(self.runs):
            yield self.outQueue.get()

    def wait(self):
        """
        Send poison pills to jobs and wait for them to finish
        The join() should kill all the processes
        """
        for t in self._threads:
            self.inQueue.put(None)

        # wait for all jobs to finish
        self.inQueue.join()
