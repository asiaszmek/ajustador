#!/usr/bin/python3

import os
import sys
import numpy as np
import ajustador as aju
import squid_experimental as squid_exp # Acutual experimental data from waves.

from ajustador import drawing
from matplotlib import pyplot

########### Optimization of Squid 2 compartment neuron ##############
ntype='squid' # neuron type.
modeltype='squid' # Neuron model.
<<<<<<< HEAD
generations=1 # 1 for test run and 250 for actual run.
popsiz=3 # 3 for test run and 8 for actual run.
=======
generations=200 # 1 for test run and 250 for actual run.
popsiz=8 # 3 for test run and 8 for actual run.
>>>>>>> 92ff80f0ba4918f932dd2cab7f1f64b7cad4bce8

################## neuron /data specific specifications #############
dataname='squid_experimental' # what should be the dataname???
neuron_file_loc = '/home/Sriramsagar/neural_prj/outputs/squid_opt/'+dataname+'tau_z_temp'
#Change directory so that outcomes*.dat will be saved to different directories
if not os.path.exists(neuron_file_loc):
    os.mkdir(neuron_file_loc)

os.chdir(neuron_file_loc)

print("squid data keys:", squid_exp.data.keys())
exp_to_fit = squid_exp.data[dataname] # TODO check for data!!! get professors help.

tmpdir='/tmp/Sriramsagar'+modeltype+'-'+ntype+'-'+dataname+'tau_z_temp'

######## setup parameters for fitness ############

P = aju.optimize.AjuParam

# without vshift and tau parameter changes.
'''
params1 = aju.optimize.ParamSet(
    P('junction_potential', 0, min=-0.020, max=0.020),
    P('Cond_K_0', 360, min=100, max=400),
    P('Cond_K_1', 560, min=200, max=600),
    P('Cond_Na_0', 1200, min=100, max=1500),
    P('Cond_Na_1', 1000, min=100, max=1500),
    P('morph_file', 'squid_10C.p', fixed=1),
    P('neuron_type',     ntype, fixed=1),
    P('model',           modeltype,     fixed=1))

'''

'''
# Start all parameters with exact parameter values of squid model.
params1 = aju.optimize.ParamSet(
    P('junction_potential', 0, min=-0.020, max=0.020),
    P('Chan_K_vshift', 0, min=-0.01, max=0.01),
    P('Chan_Na_vshift', 0, min=-0.01, max=0.01),
    P('Chan_K_taumul', 1, min=0.1, max=2),
    P('Chan_Na_taumul', 1, min=0.1, max=2),
    P('Cond_K_0', 360, min=100, max=400),
    P('Cond_K_1', 560, min=200, max=600),
    P('Cond_Na_0', 1200, min=100, max=1500),
    P('Cond_Na_1', 1000, min=100, max=1500),
    P('morph_file', 'squid_10C.p', fixed=1),
    P('neuron_type',     ntype, fixed=1),
    P('model',           modeltype,     fixed=1))
'''

# junction_potential is must and it is the threshold voltage
# Start all parameters with slight deviation to approach exact fit parameters.
params1 = aju.optimize.ParamSet(
    P('junction_potential', 0.0, min=-0.00001, max=0.002),
    P('Chan_K_vshift', 0.005, min=-0.01, max=0.01),
    P('Chan_Na_vshift', 0.005, min=-0.01, max=0.01),
    P('Chan_K_taumul', 0.5, min=0.1, max=2),
    P('Chan_Na_taumul', 0.5, min=0.1, max=2),
    P('Cond_K_0', 370, min=100, max=400),
    P('Cond_K_1', 570, min=200, max=600),
    P('Cond_Na_0', 1210, min=100, max=1500),
    P('Cond_Na_1', 1010, min=100, max=1500),
    P('Chan_Krp_taumul', 0.9, min=0.5, max=2),
    P('Chan_Krp_vshift', 0.001, min=-0.05, max=0.05),
    P('Chan_SKCa_taumul', 0.9, min=0.5, max=2),
    P('Chan_SKCa_vshift', 0.001, min=-0.05, max=0.05),
    P('morph_file', 'squid_10C.p', fixed=1),
    P('neuron_type',     ntype, fixed=1),
    P('model',           modeltype,     fixed=1))


fitness = aju.fitnesses.combined_fitness('empty',
                                         response=1,
                                         baseline_pre=1,
                                         baseline_post=1,
                                         spike_time=1,
                                         spike_width=1,
                                         spike_height=1,
                                         spike_latency=1,
                                         spike_count=1,
                                         spike_ahp=1,
                                         ahp_curve=1,
                                         spike_range_y_histogram=1)

########### Neuron and fit specific commands ############
fit1 = aju.optimize.Fit(tmpdir,
                        exp_to_fit,
                        modeltype, ntype,
                        fitness, params1,
                        _make_simulation=aju.optimize.MooseSimulation.make,
                        _result_constructor=aju.optimize.MooseSimulationResult)

fit1.load()

fit1.do_fit(generations, popsize=popsiz)

#look at results
drawing.plot_history(fit1, fit1.measurement)
