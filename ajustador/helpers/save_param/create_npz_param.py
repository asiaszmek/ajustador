import logging
import fileinput
import shutil
import numpy as np
from pathlib import Path
from ajustador.helpers.loggingsystem import getlogger
from ajustador.helpers.save_param.process_morph import find_morph_file
from ajustador.helpers.save_param.process_morph import get_morph_file_name
from ajustador.helpers.save_param.process_param_cond import get_state_machine
from ajustador.helpers.save_param.process_param_cond import process_cond_line

logger = getlogger(__name__)
logger.setLevel(logging.DEBUG)

def create_path(path,*args):
    "Creates sub-directories recursively if they are not available"
    path = Path(path)
    path = path.joinpath(*args)
    logger.debug("Path: {}".format(path))
    path.mkdir(parents=True)
    return path

def get_least_fitness_params(data, fitnum= None): # Test this made some changes.
    """ fitnum == None -> return last item least fitness parameters list.
        fitnum == integer -> return fitnum item from data(npz object).
    """
    row = fitnum if fitnum else np.argmin(data['fitvals'][:,11])
    logger.debug("row number: {}".format(row))
    return np.dstack((data['params'][row],data['paramnames']))[0]

def get_conds_non_conds(param_data_list): #identify all forms of conductances.
    logger.debug("{}".format(param_data_list))  #fix conds to get 1 _,2 _ and None.
    non_conds = {item[1]:item[0] for item in param_data_list if not item[1].startswith('Cond_')}
    logger.debug("{}".format(non_conds))
    conds = {item[1]:item[0] for item in param_data_list if item[1].startswith('Cond_')}
    logger.debug("{}".format(conds))
    logger.debug("{}".format(non_conds))
    return(conds, non_conds)


def create_npz_param(npz_file, model, neuron_type, store_param_path, fitnum=None, cond_file='param_cond.py'):
    import moose_nerp
    model_path = Path(moose_nerp.__file__.rpartition('/')[0])/model
    logger.info("START STEP 1!!!loading npz file.")
    data = np.load(npz_file)
    logger.info("END STEP 1!!! loading npz file.")

    logger.info("START STEP 2!!! Prepare params for loaded npz.")
    param_data_list = get_least_fitness_params(data, fitnum)
    logger.debug("Param_data: {}".format(param_data_list))
    conds, non_conds = get_conds_non_conds(param_data_list)
    logger.info("END STEP 2!!! Prepared params for loaded npz.")

    logger.info("START STEP 3!!! Copy file from respective prototye folder to new_param holding folder.")

    new_param_path = create_path(store_param_path, model, neuron_type)

    logger.debug("model_path {} new_path {}".format(model_path/cond_file, new_param_path))
    logger.debug("model_path type {} new_path type {}".format(type(model_path/cond_file), type(new_param_path)))
    shutil.copy(str(model_path/cond_file), str(new_param_path))
    logger.info("END STEP 3!!! Copy file from respective prototye folder to new_param holding folder.")

    logger.info("START STEP 4!!! Extract morph_file from param_cond.py file in the holding folder")
    with fileinput.input(files=(str(new_param_path/cond_file))) as f_obj:
       for line in f_obj:
           if find_morph_file(line):
               logger.debug("{}".format(find_morph_file(line)))
               logger.debug("{} {}".format(line, neuron_type))
               morph_file = get_morph_file_name(line, neuron_type)
               logger.debug("{}".format(morph_file))
               if morph_file is not None:
                  break
    logger.debug("morph_file: {}".format(morph_file))
    logger.info("END STEP 4!!! Extract the respective param_cond.py file in the holding folder")

    logger.info("START STEP 5!!! Modify the respective *.p file in the holding folder")
    Object = lambda **kwargs: type("Object", (), kwargs)
    model_obj = Object(__file__ = str(model_path), value = model)

    from ajustador.basic_simulation import morph_morph_file
    morph_morph_file(model_obj, neuron_type, str(model_path/morph_file), new_file = open(str(new_param_path/morph_file),'w'),
                 **non_conds)
    logger.info("END STEP 5!!! Modify the respective *.p file in the holding folder")
    logger.info("START STEP 6!!! Modify the param_cond.py file in the holding folder")
    with fileinput.input(files=(str(new_param_path/cond_file)), inplace=True) as f_obj:
       machine = get_state_machine(model_obj.value, neuron_type, conds)
       for line in f_obj:
           process_cond_line(line, machine)
    logger.info("END STEP 6!!! Modified the param_cond.py file in the holding folder")

    logger.info("START STEP 7!!! Renaming morph and param_cond files.")
    logger.info("{} {}".format(type(new_param_path/cond_file), type(new_param_path/morph_file)))
    #fit_name = get_fit_name(npz_file)  ## Need to discuss with Professor.
    logger.info("END STEP 7!!! Renaming morph and param_cond files.")
