#2. update d1d2, 3. test spines, etc
"""Run a single simulation from the command-line

This module takes a set of parameters which override the defaults
provides by the moose_nerp module and runs the simulation and saves the
results. In particular, this is useful when running multiple simulation
in parallel, where each one should be run out-of-process::

  $ python3 -m ajustador.basic_simulation \\
      --baseline=-0.07639880161359705 \\
      --RA=9.273975490852102 \\
      --RM=0.11241922550664576 \\
      --CM=0.0298401595465488 \\
      --Cond-Kir=6.441375022294002 \\
      --Kir-offset=6.529897906031442e-07 \\
      --morph-file=MScell-tertDendlongRE.p \\
      --simtime=0.9 \\
      -i=-5.0000000000000034e-11 \\
      --save-vm=ivdata--5.0000000000000034e-11.npy

This module is not automatically imported as a child of ajustador.
An explicit import is needed:
>>> import ajustador.basic_simulation
"""

# Basic_simulation.py is called in optimize.py as a subprocess from a different
# directory than the optimization originated in, which can mess up the python
# path if, for example, ajustador is not added globally to the python path but 
# expected to be in the current directory. This is the case for simulations on 
# the Neuroscience Gateway Portal. To rectify this, we modify the system path 
# below by getting the parent directory of the parent directory of basic_simulation

# Note: the below solution is commented out because a more robust solution has been
# implemented in optimize.py where basic_simulation gets called. Can remove these 
# commented blocks following sufficient testing.
import os
import sys
print(sys.path)
print(os.getcwd())
# file = __file__ # Get path of basic_simulation.py
# # Root directory for inserting in path should be one above parent directory
# import pathlib
# root = str(pathlib.Path(file).parent.parent)
# # insert root path into first position of system path if it's not already there
# if str(pathlib.Path(sys.path[0]).absolute()) !=root:
#     sys.path.insert(0,root)
# print(sys.path)
# print(os.getcwd())

import tempfile
import re
import importlib
import numpy as np
import moose
from moose_nerp.prototypes import (create_model_sim,
                                   cell_proto,
                                   calcium,
                                   clocks,
                                   inject_func,
                                   tables,
                                   util,
                                   standard_options
)
from moose_nerp.graph import neuron_graph
from moose_nerp.prototypes import print_params
from ajustador.regulate_chan_kinetics import chan_setting
from ajustador.regulate_chan_kinetics import scale_voltage_dependents_tau_muliplier
from ajustador.regulate_chan_kinetics import offset_voltage_dependents_vshift
from ajustador.helpers.loggingsystem import getlogger

import logging
logger = getlogger(__name__)
logger.setLevel(logging.WARNING)

def real(s):
    ''' Function to convert a value into float and raises ValueError if it is NAN.
    '''
    f = float(s)
    if np.isnan(f):
        raise ValueError
    return f

def cond_setting(s):
    "Splits 'NaF,0=123.4' → ('NaF', 0, 123.4)"
    lhs, rhs = s.split('=', 1)
    rhs = float(rhs)
    chan, comp = lhs.split(',', 1)
    if comp != ':':
        comp = int(comp)
    return chan, comp, rhs

def option_parser():
    ''' Extends moose_nerp.prototypes.standard_options by defining additional
        console arguments simulation.
    '''
    p, _ = standard_options.standard_options(
        default_injection_delay=0.2,
        default_injection_width=0.4,
        default_injection_current=[-0.15e-9, 0.15e-9, 0.35e-9],
        default_simulation_time=.9,
        default_plot_vm=None,
    )
    p.add_argument('--morph-file')
    p.add_argument('--baseline', type=real)
    p.add_argument('--model', required=True)
    p.add_argument('--neuron-type', required=True)

    p.add_argument('--RA', type=real)
    p.add_argument('--RM', type=real)
    p.add_argument('--CM', type=real)
    p.add_argument('--Erest', type=real)
    p.add_argument('--Eleak', type=real)

    p.add_argument('--Kir-offset', type=real)

    p.add_argument('--cond', default=[], nargs='+', type=cond_setting, action=standard_options.AppendFlat)
    p.add_argument('--save-vm')
    p.add_argument('--chan', default=[], nargs='+', type=chan_setting, action=standard_options.AppendFlat)
    p.add_argument('--CaPoolTauDend', type=real)
    p.add_argument('--CaPoolTauSoma', type=real)
    p.add_argument('--CaPoolBDend', type=real)
    p.add_argument('--CaPoolBSoma', type=real)

    return p

@util.listize
def serialize_options(opts):
    conds = []          # Channel conductances.
    chans = []          # Channel voltage dependent's tau multiplier and vshifts.
    for key,val in opts.items():
        if key == 'junction_potential':
            # ignore, handled by the caller
            continue
        if val is not None:
            parts = key.split('_')
            num = getattr(val, 'value', val) #if val is object return val.value else val.
            if parts[0] == 'Cond' and len(parts) == 3: # e.g. Cond_NaF_0=value
                conds.append('{},{}={}'.format(parts[1], parts[2], num))
            elif parts[0] == 'Cond' and len(parts) == 2: # e.g. Cond_Kir=value
                conds.append('{},:={}'.format(parts[1], num))
            elif parts[0] == 'Chan' and len(parts) == 4: # e.g. Chan_NaF_vshift/taumul_[X/Y/Z]=value
                chans.append('{},{},{}={}'.format(parts[1],parts[2], parts[3], num))
            elif parts[0] == 'Chan' and len(parts) == 3: # e.g. Chan_NaF_vshift/taumul=value
                chans.append('{},{},:={}'.format(parts[1], parts[2], num))
            else:
                key = key.replace('_', '-')
                yield '--{}={}'.format(key, num)
    logger.debug('{}'.format(conds))
    if conds:
        yield '--cond'
        yield from conds
    if chans: # Check how it is generating options. it should be simillar to conds.
        yield '--chan'
        yield from chans

def morph_morph_file(model, ntype, morph_file, new_file=None,
                     RA=None, RM=None, CM=None, Erest=None, Eleak=None):
    ''' Fuction to create a new_morph_file by updated values for RA, RM, CM,
        EREST_ACT and ELEAK input arguments.
    '''
    if morph_file:
        morph_file = util.find_model_file(model, morph_file)
    else:
        morph_file = cell_proto.find_morph_file(model, ntype)

    t = open(morph_file).read()

    if new_file is None:
        new_file = tempfile.NamedTemporaryFile('wt', prefix='morphology-', suffix='.p',dir=os.getcwd(), delete=False)

    for param, value in (('RA', RA),
                         ('RM', RM),
                         ('CM', CM),
                         ('EREST_ACT', Erest),
                         ('ELEAK', Eleak)):
        if value is not None:
            pat = r'(\*(set_global|set_compt_param) {})\s.*'.format(param)
            repl = r'\1 {}'.format(value)
            t_new = re.sub(pat, repl, t, count=1)
            if t_new == t:
                raise ValueError('substitution failed on {}: {!r}'.format(morph_file, pat))
            t = t_new

    new_file.write(t)
    new_file.flush()

    return new_file


def setup_CaPool(param_sim, model):
    if not any(getattr(param_sim, k, None) for k in ['CaPoolTauDend', 'CaPoolTauSoma', 'CaPoolBDend', 'CaPoolBSoma']):
        return
    if getattr(param_sim,'CaPoolTauDend',None):
        model.param_ca_plas.Taus[model.param_ca_plas.dend]=param_sim.CaPoolTauDend
    if getattr(param_sim,'CaPoolTauSoma',None):
        model.param_ca_plas.Taus[model.param_ca_plas.soma]=param_sim.CaPoolTauSoma
    if getattr(param_sim,'CaPoolBDend',None):
        model.param_ca_plas.BufferCapacityDensity[model.param_ca_plas.dend]=param_sim.CaPoolBDend
    if getattr(param_sim,'CaPoolBSoma',None):
        model.param_ca_plas.BufferCapacityDensity[model.param_ca_plas.dend]=param_sim.CaPoolBSoma
    for k,v in model.param_ca_plas.CaShellModeDensity.items():
        model.param_ca_plas.CaShellModeDensity[k] = model.param_ca_plas.CAPOOL


def setup_conductance(condset, name, index, value):
    ''' Updates condset object's attribute with name.
        index == ':' -> Sets all child members values of condset.name
                        with value(input argument).
        index != ':' -> Set specific child member value of condset.name
                        with value(input argument).
    distance dependent conductances.
    '''
    attr = getattr(condset, name)
    keys = sorted(list(attr.keys())) # sorted ensures keys are in order of distance from soma
    if index == ':':
        for k in keys:
            attr[k] = value
    else:
        try:
            attr[keys[index]] = value
        except IndexError: # This exception gives an idea, where to check for the error.
            raise IndexError("Please check definitions of {} param conductances in param_cond.py conductances!!!".format(name))

def setup(param_sim, model):
    #these next two overrides are not used in optimization as they are not passed in from optimize
    #they could be used if running basic_simulation directly
    '''
    if param_sim.calcium is not None:
        model.calYN = param_sim.calcium
    if param_sim.spines is not None:
        model.spineYN = param_sim.spines
     '''

    '''
    if model.type = nml:
        this block of code updates neuroml files
        write a bunch of new  code
    else:
        #this block of code updates moose_nerp foramt files
    '''
    condset = getattr(model.Condset, param_sim.neuron_type) # Fetch reference for model condutances.
    chanset = model.Channels                                # Fetch reference for model channels.

    for cond in sorted(param_sim.cond):
        name, comp, value = cond
        if logger.level == logging.DEBUG:
            print('cond:', name, comp, value)
        setup_conductance(condset, name, comp, value)

    for chan in param_sim.chan:
        chan_name, opt, gate, value  = chan
        if logger.level == logging.DEBUG:
            print('chan:', chan_name, opt, gate, value)
        if opt == 'taumul':
           scale_voltage_dependents_tau_muliplier(chanset, chan_name, gate, value)
        elif opt == 'vshift':
           offset_voltage_dependents_vshift(chanset, chan_name, gate, value)

    new_file = morph_morph_file(model,
                                param_sim.neuron_type,
                                param_sim.morph_file,
                                RA=param_sim.RA, RM=param_sim.RM, CM=param_sim.CM,
                                Erest=param_sim.Erest, Eleak=param_sim.Eleak)
    logger.info('morph_file: {}'.format(new_file.name))
    model.morph_file[param_sim.neuron_type] = new_file.name
    #end of code that updates moose_nerp files

    plotcomps=[model.param_cond.NAME_SOMA]
    fname=param_sim.neuron_type+'.h5'
    param_sim.save=1
    #create neuron model and set up output
    model.param_sim = param_sim
    setup_CaPool(param_sim, model)
    #syn,neurons,writer,tables=create_model_sim.create_model_sim(model,fname,param_sim,plotcomps)
    create_model_sim.setupNeurons(model)
    #set up current injection
    neuron_paths = {ntype:[neuron.path]
                    for ntype, neuron in model.neurons.items()}
    pg = inject_func.setupinj(model, param_sim.injection_delay, param_sim.injection_width, neuron_paths)
    writer=None#tables.setup_hdf5_output(model, model.neurons, filename=fname,                                 compartments=plotcomps)
    tables.graphtables(model, model.neurons, model.param_sim.plot_current,
                       model.param_sim.plot_current_message, model.plas,
                       plotcomps)
    if logger.level==logging.DEBUG:
        print_params.print_elem_params(model,param_sim.neuron_type,param_sim)
    return pg, writer

def reset_baseline(neuron, baseline, Cond_Kir):
    for n, w in enumerate(moose.wildcardFind('/{}/#[TYPE=Compartment]'.format(neuron))):
        w.initVm = w.Vm = baseline

        if Cond_Kir != 0:
            kir = moose.element(w.path + '/Kir')
            Em = baseline + kir.Gk * w.Rm * (baseline - kir.Ek)
            if n == 0:
                print("%s Em %f -> %f" % (w.path, w.Em, Em))
            w.Em = Em

def run_simulation(injection_current, simtime, param_sim, model):
    global pulse_gen
    if logger.level == logging.DEBUG:
        print("################## moose versions: ", moose.__version__)
    print(u'************* injection_current = {} ******'.format(injection_current))
    pulse_gen.firstLevel = injection_current
    moose.reinit()
    if param_sim.baseline is not None:
        condset = getattr(model.Condset, param_sim.neuron_type)
        try:
            attr = condset.Kir
        except KeyError:
            pass
        else:
            keys = sorted(attr.keys())  #Check is this effecting cond Kir when 'axon' in dist, med param_cond?
            Cond_Kir = attr[keys[0]]
            reset_baseline(param_sim.neuron_type, param_sim.baseline, Cond_Kir)
    moose.start(simtime)

def main(args):
    global param_sim, pulse_gen
    param_sim = option_parser().parse_args(args)
    model = importlib.import_module('moose_nerp.' + param_sim.model)
    model.param_cond.neurontypes=util.neurontypes(model.param_cond,[param_sim.neuron_type])
    logger.debug("param_sim::::::::: {}".format(param_sim))
    pulse_gen, hdf5writer = setup(param_sim, model)
    run_simulation(param_sim.injection_current[0], param_sim.simtime, param_sim, model)
    #hdf5writer.close()

    if param_sim.plot_vm:
        neuron_graph.graphs(model,model.vmtab, param_sim.plot_current, param_sim.simtime, compartments=[0])
        util.block_if_noninteractive()
    if param_sim.save_vm:
        elemname = '/data/Vm{}_0'.format(param_sim.neuron_type)
        np.save(param_sim.save_vm, moose.element(elemname).vector)

if __name__ == '__main__':
    main(sys.argv[1:])
