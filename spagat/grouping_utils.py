import xarray as xr
import numpy as np
import pandas as pd

from sklearn import preprocessing as prep
from scipy.cluster import hierarchy

def preprocessTimeSeries(vars_dict, n_components):
    '''Preprocess the input dictionary of time series variables
        - Input vars_dic: dimensions of each variable value are 'component','space','TimeStep'
        - Output ds_ts: a dictionary containing all variables
            - For each variable: the value is a dictionary containing all its valid components
            - For each variable and each valid component: 
                - the value is a numpy array of size n_regions * TimeStep         
                - the array is normalized  ?and weighted by the variable weight factors ?     
    '''
    if not vars_dict: return None

    ds_ts = {}

    for var, da in vars_dict.items():

        ds_ts_var = {}

        # Find the valid components for each variable
        var_mean_df = da.mean(dim="space").mean(dim="TimeStep").to_dataframe()
        var_mean_df['component_id'] = np.array(range(n_components))
        valid_component_ids = list(var_mean_df[var_mean_df[var].notna()]['component_id'])

        # Concatenate the normalized matrix for each valid component
        for comp_id in valid_component_ids:
            ds_ts_var[comp_id] = prep.scale(da[comp_id].values) 

        ds_ts[var] = ds_ts_var
           
    return ds_ts

def preprocess1dVariables(vars_dict, n_components):
    ''' Preprocess 1-dimensional variables
        - return a dictionary containing all 1d variables
        - each value is a numpy array of size n_regions * n_valid_components_of_each_variable, e.g. 96*6 for '1d_capacityFix'
    '''

    if not vars_dict: return None

    ds_1d = {}

    for var, da in vars_dict.items():
        
        # Find the valid components for each variable
        var_mean_df = da.mean(dim="space").to_dataframe()
        var_mean_df['component_id'] = np.array(range(n_components))
        valid_component_ids = list(var_mean_df[var_mean_df[var].notna()]['component_id'])
        

        # Only remain the valid components
        data = da.values[valid_component_ids]
        ds_1d[var] = prep.scale(data.T)

    return ds_1d

def preprocess2dVariables(vars_dict, component_list, handle_mode='toDissimilarity'):
    ''' Preprocess matrices of 2d-vars with one of the following mode:
        - Firstly: Adjust the region order of space_2, i.e. order of columns
        - Obtain ds_2d: a dictionary containing all variables
            - For each variable: the value is a dictionary containing all its valid components
            - For each variable and each valid component: 
                - the value is a numpy array of size n_regions*n_regions
                - the matrix is symmetrical. (undirected graph), with zero diagonal values
                - all the values in the matrices are NON-Negative!

        - Return: a dictionary containing a matrix / vector for each 2d var and each component
            - standardize the vector (rescaling!)
            - Possible TO-DO: add the matrics together?

        How to handle the matrices:
            - handle_mode == 'toDissimilarity': Convert matrices to a distance matrix by transforming the connectivity values to distance meaning
            - handle_mode='extract': extract the matrices of all variables and add them up as one adjacency matrix for spectral clustering
    '''

    if not vars_dict: return None

    n_components = len(component_list)

    # Obtain th dictionary of connectivity matrices for each variable and for its valid component, each of size 96*96 (n_regions)
    ds_2d = {}

    for var, da in vars_dict.items():
        
        ds_2d_var = {}
        
        # Different region orders
        space1 = da.space.values
        space2 = da.space_2.values
        
        # Find the valid components for each variable
        var_mean_df = da.mean(dim="space").mean(dim="space_2").to_dataframe()
        var_mean_df['component_id'] = np.array(range(n_components))
        valid_component_ids = list(var_mean_df[var_mean_df[var].notna()]['component_id'])
        
        # DataArray da for this 2d-variable, component:29 * space:96 * space_2:96
        for comp_id in valid_component_ids:
            
            # Under each component, there is a 96*96 squares matrix to represent the connection features
            var_matr = da[comp_id].values
            
            # Rearrange the columns order --> the regions order of space_2!
            da_comp_df = pd.DataFrame(data=var_matr,columns=space2)
            da_comp_df = da_comp_df[space1]
            
            ds_2d_var[comp_id] = da_comp_df.to_numpy()
        
        ds_2d[var] = ds_2d_var

    # Handle the matrices according to clustering methods

    ## Possible TO-DO: maybe other transformation methods are possible, e.g. Gaussian (RBF, heat) kernel
    if handle_mode == 'toDissimilarity':
        ''' Convert similarity matrix (original symmetric connectivity matrix) into dissimilarity matrix (1-dim Distance vector)
            - higher values for connectivity means: the two regions are more likely to be grouped -> can be regarded as smaller distance!
            
            - Rescaling the connectivity matrix to range [0,1], where 1 means maximum similarity
            - dissim(x) = 1 - sim(x)
        '''

        # Obtain a dictionary containing one distance vector (1-dim matrix) for each variable and for each valid component
 
        min_max_scaler = prep.MinMaxScaler()

        for var, var_dict in ds_2d.items():
            
            # Transform the symmetric connectivity matrix to 1-dim distance vector
            for c, data in var_dict.items():
                
                # Obtain the vector form of this symmetric connectivity matrix
                vec = hierarchy.distance.squareform(data)

                # Standardize it: keep all the values non-negative! AND keep zeros to be zeros (not change the meaning of connectivity!)
                # => scale the data to the range [0,1]
                vec = np.reshape(vec, (-1,1))
                vec = min_max_scaler.fit_transform(vec)
                vec = np.reshape(vec, (1,-1))[0]

                # Convert the value of connectivity (similarity) to distance (dissimilarity)
                vec = 1 - vec
                
                # Distance vector for this 2d variable and this component: 1 means maximum distance!
                ds_2d[var][c] = vec
  
        return ds_2d

    if handle_mode == 'extract':
        '''2d variables -> Adjacency matrix : 
            - add all matrices from various variables (## TO-DO:and various components)
            - adjacency matrix of a graph: symmetric, diagonals = 0
        '''

        part2 = dataset[vars_list[0]].values
        part2[np.isinf(part2)] = 100000
        part2[np.isnan(part2)] = 0
        part2 = part2 * weight_factors.get(vars_list[0])

        for var in vars_list[1:]:
            var_matrix = dataset[var].values
            var_matrix[np.isinf(var_matrix)] = 100000
            var_matrix[np.isna(var_matrix)] = 0
            part2 += var_matrix * weight_factors.get(var)

        return part2

def preprocessDataset(sds,vars='all',dims='all',handle_mode='toDissimilarity'):
    '''Preprocess the Xarray dataset: Separate the dataset into 3 parts: time series data, 1d-var data, and 2d-var data
        - vars_ts: Time series variables  
            - sub distances based on timesteps and based on components 
            - e.g. dist = sum(dist_t0_c1 + dist_t0_c2 + dist_t1_c1 + ...)
        - vars_1d: 1d variables as features matrix
        - vars_2d: 2d variables showing connectivity between regions
            - Hierarchical: directly transformed as distance matrix (reciprocal of element values) and combine with vars_ts and vats_1d
            - Spectral: extract this part as an affinity matrix for the (un)directed graph (indicating similarity, here using adjacency matrix)
            - handle_mode: decide which method to preprocess vars_2d

        - Return: the three parts separately 
    '''

    dataset = sds.xr_dataset

    # Traverse all variables in the dataset, and put them in separate categories
    vars_ts = {}
    vars_1d = {}
    vars_2d = {}

    for varname, da in dataset.data_vars.items():
        if da.dims == ('component','Period','TimeStep', 'space'):
            # Do not have to consider the Period --> ToDo: consider the Period dimension.
            da = da.transpose('Period','component','space','TimeStep')[0]  
            vars_ts[varname] = da

        if da.dims == ('component','space'):
            vars_1d[varname] = da

        if da.dims == ('component','space','space_2'):
            vars_2d[varname] = da

    component_list = list(dataset['component'].values)

    n_regions = len(dataset['space'].values)

    ds_timeseries = preprocessTimeSeries(vars_ts, len(component_list))
    ds_1d_vars = preprocess1dVariables(vars_1d, len(component_list))
    ds_2d_vars = preprocess2dVariables(vars_2d, component_list, handle_mode='toDissimilarity')

    return ds_timeseries, ds_1d_vars, ds_2d_vars


def selfDistance(ds_ts, ds_1d, ds_2d, n_regions, a, b, var_weightings=None):
    ''' Custom distance function: 
        - parameters a, b: region ids, a < b, a,b in [0, n_regions)
        - return: distance between a and b = distance_ts + distance_1d + distance_2d
            - distance for time series: ** dist_var_component_timestep ** -> value subtraction
            - distance for 1d vars: sum of (value subtraction in ** dist_var_component ** )
            - distance for 2d vars: corresponding value in ** dist_var_component **
            - each partial distance need to be divided by sum of variable weight factors, 
                i.e. number of variables when all weight factors are 1, 
                to reduce the effect of variables numbers on the final distance.
        ---
        Metric space properties :  -> at the same level of data structure! in the same distance space!
        - Non-negativity: d(i,j) > 0
        - Identity of indiscernibles: d(i,i) = 0   ---> diagonal must be 0!
        - Symmetry: d(i,j) = d(j,i)  ---> the part_2 must be Symmetrical!
        - Triangle inequality: d(i,j) <= d(i,k) + d(k,j)  ---> NOT SATISFIED!!!
    '''
    # i= a[0]
    # n = int(a[1])

    # distance_part_1 = np.linalg.norm(a[2:2+n]-b[2:2+n]) if n != 0 else 0
    # distance_part_2 = b[n+int(i)+2] if np.isnan(b[2+n]) else 0

    # Weighting factors of each variable 
    if var_weightings:
        var_weightings = var_weightings
    else:
        vars_list = list(ds_ts.keys()) + list(ds_1d.keys()) + list(ds_2d.keys())
        var_weightings = dict.fromkeys(vars_list,1)

    # Distance of Time Series Part
    distance_ts, l_ts = 0, 0
    for var, var_dict in ds_ts.items():

        var_weight_factor = var_weightings[var]

        for component, data in var_dict.items():
            
            l_ts += data.shape[1] * var_weight_factor
            
            reg_a_vector = data[a]
            reg_b_vector = data[b]

            distance_ts += sum(abs(reg_a_vector-reg_b_vector)) * var_weight_factor

    distance_ts = distance_ts / l_ts

    # Distance of 1d Variables Part
    distance_1d, l_1d = 0, 0
    for var, data in ds_1d.items():

        var_weight_factor = var_weightings[var]
        l_1d += data.shape[1] * var_weight_factor

        distance_1d += sum(abs(data[a] - data[b])) * var_weight_factor
    
    distance_1d = distance_1d / l_1d

    # Distance of 2d Variables Part
    distance_2d, l_2d = 0, 0

    # The index of corresponding value for region[a] and region[b] in the distance vectors
    index_regA_regB = a * (n_regions - a) + (b - a) -1
    
    for var, var_dict in ds_2d.items():

        var_weight_factor = var_weightings[var]
        l_2d += len(var_dict.keys()) * var_weight_factor

        for component, data in var_dict.items():

            # Find the corresponding distance value for region_a and region_b
            distance_2d += data[index_regA_regB]

    distance_2d = distance_2d / l_2d


    return distance_ts + distance_1d + distance_2d

def selfDistanceMatrix(ds_ts, ds_1d, ds_2d, n_regions):
    ''' Return a n_regions by n_regions symmetric distance matrix X 
    '''

    distMatrix = np.zeros((n_regions,n_regions))

    for i in range(n_regions):
        for j in range(i+1,n_regions):
            distMatrix[i,j] = selfDistance(ds_ts,ds_1d, ds_2d, n_regions, i,j)

    distMatrix += distMatrix.T - np.diag(distMatrix.diagonal())

    return distMatrix
