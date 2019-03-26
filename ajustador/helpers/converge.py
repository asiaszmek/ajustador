import numpy as np

import glob
from scipy import optimize

def line(x,A,B):
        return B*x+A

def calc_mean_slopes(array_item,slope_test_size,test_size):
    slope=np.zeros(slope_test_size)
    mean=np.zeros(slope_test_size)
    std=np.zeros(slope_test_size)
    for i in range(slope_test_size):
            popt,pcov=optimize.curve_fit(line,list(range(test_size)),
                                         array_item[i*test_size:(i+1)*test_size])
            Aopt,Bopt=popt
            slope[i]=Bopt
            mean[i]=np.mean(array_item[i*test_size:(i+1)*test_size]) #Aopt
            std[i]=np.std(array_item[i*test_size:(i+1)*test_size])
    return {'mean':mean,'std':std,'slope':slope}

def converge_dict(fit_values,test_size,popsiz):
    generations=int(np.round(len(fit_values)/popsiz))
    means=np.zeros(generations)
    stdev=np.zeros(generations)
    for i in range(generations):
        means[i]=np.mean(fit_values[i*popsiz:(i+1)*popsiz])
        stdev[i]=np.std(fit_values[i*popsiz:(i+1)*popsiz])
        CV=stdev/means
    if test_size>0:
            slope_test_size=int(np.round(generations/test_size))
            mean_dict=calc_mean_slopes(means,slope_test_size,test_size)
            std_dict=calc_mean_slopes(stdev,slope_test_size,test_size)
    else:
            mean_dict={'mean':means,'std':np.zeros(len(means)),'slope':np.zeros(len(means))}
            std_dict={'mean':stdev,'std':np.zeros(len(stdev)),'slope':np.zeros(len(stdev))}
    return mean_dict,std_dict,CV

def iterate_fit(fitX,test_size,popsiz,slope_crit=2e-3, std_crit=0.06,max_evals=5000):
    # 0.04 criteria looked better for GPE, even .02; Might need as many as 10000 evals
    #
    converge=False
    last_j=0
    #print('iterate_fit.py: len of fitness',len(fitX))
    with open("convergence.dat","w") as fitfile:
        fitfile.write("data name: "+str(fitX.name)+"  test_size: "+str(test_size)+"\n")
        fitfile.write("iter mean_mean std_mean slope_mean mean_std std_std slope_std \n")
        while not converge and len(fitX) < max_evals:
            fitX.do_fit(test_size, popsize=popsiz,seed=last_j*last_j)  #OPTIMIZE FOR ANOTHER TEST_SIZE GENERATIONS
            # calculate mean and std of the fitness values
            mean_dict, std_dict, CV = converge_dict(fitX._history, test_size, popsiz)
            for j in range(last_j,len(mean_dict['mean'])):
                line=str(j)+'  '   #write the latest fitness values to the file
                for key in mean_dict.keys():
                        line=line+'   '+str(np.round(mean_dict[key][j],5))
                for key in std_dict.keys():
                        line=line+'   '+str(np.round(std_dict[key][j],5))
                fitfile.write(line+'\n')
                #possibly divide both by mean_dict['mean'] (may need to 2x or 3x the criteria) so that convergence scales with fit?
                if np.abs(mean_dict['slope'][j])<slope_crit and mean_dict['std'][j]<std_crit:
                        converge=True                    #above tests the latest fitness value for convergence
                        print('*************** optimization converged at', j*test_size*popsiz, 'with m=',mean_dict['mean'][j] )
                else:
                        print('**************  optimization NOT converged', j*test_size*popsiz,'m=',mean_dict['mean'][j])
            last_j=j+1
            #print('last_j',j,'new range', list(range(last_j,last_j+1)))
    print('end of iterate_fit.py', fitX.name, 'len of fitness',len(fitX), 'last_j', last_j,'len(mean_dict)',len(mean_dict['mean']))
    return mean_dict,std_dict,CV
