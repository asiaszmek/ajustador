# -*- coding: utf-8 -*-
#!/usr/bin/env python3
import re
import sys
import fileinput
import importlib
from collections import defaultdict
from moose_nerp.prototypes.chan_proto import TypicalOneD
from moose_nerp.prototypes.chan_proto import TwoD
from ajustador.helpers.copy_param.process_common import test_block_comment

def create_chan_param_relation(new_param_chan, start_block_lineno, end_block_lineno):
    ''' Creates a dictionary whose key is channel (eg: Na) and values are set of parameters names which can be
        cross referred to param_chan.py file.
    '''
    valid_line_pattern = "(?P<chan>\w+)\s*=\s*(?P<func>\w+)\((?P<chanparams>[a-z0-9A-Z_,\s\[\]=]+).*"
    chan_param_relation = dict()
    with fileinput.input(files=(new_param_chan)) as f_obj:
        for line in f_obj:
            if start_block_lineno < f_obj.lineno() < end_block_lineno:
                re_obj = re.search(valid_line_pattern, line)
                if re_obj:
                    chan_name, chan_func, chan_params = re_obj.group('chan'),re_obj.group('func'), re_obj.group('chanparams')
                    # NOTE Order of calciumpermeable and calciumdependent should be strictly maintained if used for anlysis for correct working of code.
                    chan_param_relation[chan_name] = globals().get(chan_func)(*[sub_str.strip() for sub_str in chan_params.split(',')])
    return chan_param_relation

def reshape_chans_to_dict(chans):
    """ Re structure channel dictionary."""
    chans_dict = dict()
    for key, value in chans.items():
        if key.count('_') == 2:
            chan_name, attribute, gate = key.split('_')[1], key.split('_')[2], ':'
        elif key.count('_') == 3:
             chan_name, attribute, gate = key.split('_')[1], key.split('_')[2], key.split('_')[3]
        chans_dict[(chan_name, attribute, gate)] = value
    return chans_dict

def import_param_chan(model):
    import_pattern = '.'.join(['moose_nerp', model, 'param_chan'])
    imported = importlib.import_module(import_pattern)
    return imported

def chan_param_locator(new_param_chan, chan_param_relation):
    structure = defaultdict(lambda : {'start': None,'end': None, 'type': None})
    invalid_key_formats = (False, 'None', True, '[]')
    # TODO:  change the channel structure based on new dict format.
    for _list in chan_param_relation.values():
        for param in _list[1:]:
            try:
                if (isinstance(param, str) and '=' in param) or param == False or param == 'None' or param == '[]':
                    continue
                structure[param]
            except TypeError:
                continue

    valid_start_line_pattern = "^(?P<paramname>\w+)\s*=\s*(?P<paramtype>\w+)\(.*$"
    valid_end_line_pattern = "\s*([a-zA-Z_]+\s*=\s*[\-0-9\.]+e?-?[0-9]*)?\)$"
    valid_line_pattern = valid_start_line_pattern
    with fileinput.input(files=(new_param_chan)) as f_obj:
        line = next(f_obj)
        flag_block_comment = test_block_comment(line)
        for lineno, line in enumerate(f_obj, 1):
            flag_block_comment = test_block_comment(line, flag_block_comment)
            if flag_block_comment:
                continue
            re_obj = re.search(valid_line_pattern, line)
            if re_obj and valid_line_pattern == valid_start_line_pattern:
                param_name, param_type = re_obj.group('paramname'), re_obj.group('paramtype')
                if structure.get(param_name):
                    valid_line_pattern = valid_end_line_pattern
                    structure.get(param_name)['type'] = param_type
                    if not structure.get(param_name).get('start'):
                       structure.get(param_name)['start'] = lineno

            elif re_obj and valid_line_pattern == valid_end_line_pattern:
                if structure.get(param_name):
                    valid_line_pattern = valid_start_line_pattern
                    if not structure.get(param_name).get('end'):
                       structure.get(param_name)['end'] = lineno
    return structure

def get_chan_name_data_index(param_name, chan_param_name_relation):
    data_index = None
    for chan_name in chan_param_name_relation.keys():
        try:
            data_index = chan_param_name_relation[chan_name].index(param_name)
            return (chan_name, data_index)
        except ValueError:
            continue
    raise ValueError('Unable to find {} in param_chan.py!!!!'.format(param_name))

def update_chan_param(new_param_chan, chan_param_name_relation, chan_param_data_relation, param_location):
    ''' Replaces channel parameter code block with updated channel parameter code block in file.
        old_code block =
        Na_h_params = AlphaBetaChannelParams(A_rate=80.02882110535691,
                                             A_B=0.0,
                                             A_C=0.0,
                                             A_vhalf=0.07442075789034752,
                                             A_vslope=0.02,
                                             B_rate=1143.26887293367,
                                             B_B=0.0,
                                             B_C=1.0,
                                             B_vhalf=0.04442075789034753,
                                             B_vslope=-0.01)

        new_code block =
        Na_h_params = AlphaBetaChannelParams(A_rate=<updated_value>,
                                             A_B=<updated_value>,
                                             A_C=<updated_value>,
                                             A_vhalf=<updated_value>,
                                             A_vslope=<updated_value>,
                                             B_rate=<updated_value>,
                                             B_B=<updated_value>,
                                             B_C=<updated_value>,
                                             B_vhalf=<updated_value>,
                                             B_vslope=<updated_value>)

    '''
    valid_start_line_pattern = "^(?P<paramname>\w+)\s*=\s*(?P<paramtype>\w+)\(.*,$"
    valid_line_pattern = valid_start_line_pattern
    start_lineno, end_lineno = (0, 0)

    with fileinput.input(files=(new_param_chan), inplace=True) as f_obj:
        line = next(f_obj)
        flag_block_comment = test_block_comment(line)
        for lineno, line in enumerate(f_obj, 1):
                flag_block_comment = test_block_comment(line, flag_block_comment)
                if flag_block_comment:
                    sys.stdout.write(line)
                    continue
                re_obj = re.search(valid_line_pattern, line)
                if re_obj:
                    param_name, param_type = re_obj.group('paramname'), re_obj.group('paramtype')
                    chan_name, index = get_chan_name_data_index(param_name, chan_param_name_relation)
                    data_chunk = chan_param_data_relation[chan_name][index]
                    print(param_name, '=', str(data_chunk).replace(',', ',\n'))
                    start_lineno, end_lineno = param_location.get(param_name).get('start'), param_location.get(param_name).get('end')
                elif start_lineno < lineno <= end_lineno:
                     continue
                else:
                    sys.stdout.write(line)
