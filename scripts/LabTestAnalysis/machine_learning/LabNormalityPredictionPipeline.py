#!/usr/bin/python
"""
Pipeline class for managing end to end training, testing,
and analysis of LabNormality prediction.
"""

import inspect
import os
from pandas import DataFrame, Series
from sklearn.externals import joblib
from sklearn.metrics import make_scorer, average_precision_score
import logging

from medinfo.common.Util import log
from medinfo.ml.FeatureSelector import FeatureSelector
from medinfo.dataconversion.FeatureMatrixTransform import FeatureMatrixTransform
from medinfo.dataconversion.FeatureMatrixIO import FeatureMatrixIO
from medinfo.ml.BifurcatedSupervisedClassifier import BifurcatedSupervisedClassifier
from medinfo.ml.SupervisedClassifier import SupervisedClassifier
from medinfo.ml.SupervisedLearningPipeline import SupervisedLearningPipeline
from extraction.LabNormalityMatrix import LabNormalityMatrix

# Import FMF in order to retrieve all races name dynamically upon accessing the UMich data
from medinfo.dataconversion.FeatureMatrixFactory import FeatureMatrixFactory
import LocalEnv
import prepareData_NonSTRIDE
import pickle

class LabNormalityPredictionPipeline(SupervisedLearningPipeline):
    def __init__(self, lab_panel, num_episodes, use_cache=None, random_state=None, isLabPanel=True,
                 timeLimit=None, notUsePatIds=None, holdOut=False):
        self.notUsePatIds = notUsePatIds
        SupervisedLearningPipeline.__init__(self, lab_panel, num_episodes, use_cache, random_state,
                                            isLabPanel, timeLimit, holdOut,
                                            isLabNormalityPredictionPipeline=True)
        self._factory = FeatureMatrixFactory()
        self._build_raw_feature_matrix()
        self._build_baseline_results() #TODO: prototype in SLPP

        data_lab_folder = self._fetch_data_dir_path(inspect.getfile(inspect.currentframe()))
        feat2imputed_dict_path = data_lab_folder + '/feat2imputed_dict.pkl'

        if holdOut:
            '''
            For holdOut evaluation data, produce the raw matrix, pick 
            features according to the saved feat2imputed_dict. 
            '''
            self.feat2imputed_dict = pickle.load(open(feat2imputed_dict_path, 'r'))
            self._build_processed_feature_matrix_holdout()
            self._analyze_predictors_on_holdout()
        else:
            '''
            For training/validation data, record the pat_ids, 
            selected features and their imputed value correspondingly. 
            '''

            pickle.dump(self.used_patient_set, open('data/used_patient_set_%s.pkl'%self._var, 'w'), pickle.HIGHEST_PROTOCOL)
            self.feat2imputed_dict = {}
            self._build_processed_feature_matrix()
            # TODO: find better place to put the dict.pkl
            pickle.dump(self.feat2imputed_dict, open(feat2imputed_dict_path, 'w'), pickle.HIGHEST_PROTOCOL)
            # self._train_and_analyze_predictors()

    def _build_model_dump_path(self, algorithm):
        template = '%s' + '-normality-%s-model.pkl' % algorithm
        pipeline_file_name = inspect.getfile(inspect.currentframe())
        return SupervisedLearningPipeline._build_model_dump_path(self, template, \
            pipeline_file_name)

    def _build_raw_matrix_path(self):
        if not self._holdOut:
            template = '%s-normality-matrix-%d-episodes-raw.tab'
        else:
            template = '%s-normality-matrix-%d-episodes-raw-holdout.tab'
        pipeline_file_name = inspect.getfile(inspect.currentframe())
        return SupervisedLearningPipeline._build_matrix_path(self, template, \
            pipeline_file_name)

    def _build_raw_feature_matrix(self):
        raw_matrix_path = self._build_raw_matrix_path()
        matrix_class = LabNormalityMatrix
        SupervisedLearningPipeline._build_raw_feature_matrix(self, matrix_class, \
            raw_matrix_path)

    def _build_baseline_results(self):
        if not self._holdOut:
            template = '%s-normality-matrix-%d-episodes-raw.tab'
        else:
            template = '%s-normality-matrix-%d-episodes-raw-holdout.tab'
        pipeline_file_name = inspect.getfile(inspect.currentframe())
        raw_matrix_path = SupervisedLearningPipeline._build_matrix_path(self, template, \
                                                             pipeline_file_name)
        # Another direct call to the _factory instance
        self._factory.obtain_baseline_results(raw_matrix_path=raw_matrix_path,
                                              random_state=self._random_state,
                                              isLabPanel=self._isLabPanel) #TODO: file name

    def _build_processed_matrix_path(self):
        if not self._holdOut:
            template = '%s-normality-matrix-%d-episodes-processed.tab'
        else:
            template = '%s-normality-matrix-%d-episodes-processed-holdout.tab'
        pipeline_file_path = inspect.getfile(inspect.currentframe())
        return SupervisedLearningPipeline._build_matrix_path(self, template, \
            pipeline_file_path)

    def _build_processed_feature_matrix_holdout(self):
        fm_io = FeatureMatrixIO()
        raw_matrix = fm_io.read_file_to_data_frame(self._build_raw_matrix_path())

        if self._isLabPanel:
            outcome_label = 'all_components_normal'
        else:

            outcome_label = 'component_normal'

        processed_matrix = raw_matrix[self.feat2imputed_dict.keys()+[outcome_label]].copy()

        for feat in self.feat2imputed_dict.keys():
            processed_matrix[feat] = processed_matrix[feat].fillna(self.feat2imputed_dict[feat])

        fm_io.write_data_frame_to_file(processed_matrix, \
                                       self._build_processed_matrix_path(), None)

    def _build_processed_feature_matrix(self):
        # Define parameters for processing steps.
        params = {}
        raw_matrix_path = self._build_raw_matrix_path()
        processed_matrix_path = self._build_processed_matrix_path()
        features_to_add = {}
        imputation_strategies = {
        }

        if LocalEnv.DATASET_SOURCE_NAME == 'STRIDE':
            features_to_remove = [
                'pat_id', 'order_time', 'order_proc_id',
                'Birth.pre',
                'Male.preTimeDays', 'Female.preTimeDays',
                'RaceWhiteHispanicLatino.preTimeDays',
                'RaceWhiteNonHispanicLatino.preTimeDays',
                'RaceHispanicLatino.preTimeDays',
                'RaceAsian.preTimeDays',
                'RaceBlack.preTimeDays',
                'RacePacificIslander.preTimeDays',
                'RaceNativeAmerican.preTimeDays',
                'RaceOther.preTimeDays',
                'RaceUnknown.preTimeDays',
                'Death.post',
                'Death.postTimeDays'
            ]
            if self._isLabPanel:
                features_to_remove += ['proc_code', 'num_components', 'num_normal_components', 'abnormal_panel']
                outcome_label = 'all_components_normal'  #
            else:
                features_to_remove += ['base_name']
                outcome_label = 'component_normal' # TODO: danger, previous version might not consistent!

        else:
            features_to_remove = [
                'pat_id', 'order_time', 'order_proc_id',
                'Birth.pre',
                'Male.preTimeDays', 'Female.preTimeDays',
                # 'Caucasian.preTimeDays',
                # 'Hispanic.preTimeDays',
                # 'Native Hawaiian and Other Pacific Islander.preTimeDays'
            ]
            RACE_FEATURES = self._factory.queryAllRaces()
            features_to_remove += [x + '.preTimeDays' for x in RACE_FEATURES]
            if self._isLabPanel:
                features_to_remove += ['proc_code', 'num_normal_components', 'num_components']
                outcome_label = 'all_components_normal'
            else:
                features_to_remove += ['base_name']

                outcome_label = 'component_normal' #

        features_to_keep = [
            # Keep the # of times it's been ordered in past, even if low info.
            '%s.pre' % self._var
        ]

        selection_problem = FeatureSelector.CLASSIFICATION
        selection_algorithm = FeatureSelector.RECURSIVE_ELIMINATION
        percent_features_to_select = 0.05
        matrix_class = LabNormalityMatrix
        pipeline_file_path = inspect.getfile(inspect.currentframe())
        random_state = self._random_state
        data_overview = [
            # Overview:
            'Overview',
            # The outcome label is ___.
            'The outcome label is %s.' % outcome_label,
            # %s is a boolean indicator which summarizes whether all components
            '%s is a boolean indicator which summarizes whether all components ' % outcome_label,
            # in the lab panel order represented by a given row are normal.
            'in the lab panel order represented by a given row are normal.',
            # Each row represents a unique lab panel order.
            'Each row represents a unique lab panel order.',
            # Each row contains fields summarizing the patient's demographics,
            "Each row contains fields summarizing the patient's demographics",
            # inpatient admit date, prior vitals, and prior lab results.
            'inpatient admit date, prior vitals, and prior lab results.',
            # Most cells in matrix represent a count statistic for an event's
            "Most cells in matrix represent a count statistic for an event's",
            # occurrence or a difference between an event's time and index_time.
            "occurrence or a difference between an event's time and index_time.",
        ]

        # Bundle parameters into single object to be unpacked in SLP.
        params['raw_matrix_path'] = raw_matrix_path
        params['processed_matrix_path'] = processed_matrix_path
        params['features_to_add'] = features_to_add
        params['features_to_keep'] = features_to_keep
        params['imputation_strategies'] = imputation_strategies
        params['features_to_remove'] = features_to_remove
        params['outcome_label'] = outcome_label
        params['selection_problem'] = selection_problem
        params['selection_algorithm'] = selection_algorithm
        params['percent_features_to_select'] = percent_features_to_select
        params['matrix_class'] = matrix_class
        params['pipeline_file_path'] = pipeline_file_path
        params['data_overview'] = data_overview
        params['random_state'] = random_state

        # Defer processing logic to SupervisedLearningPipeline.
        SupervisedLearningPipeline._build_processed_feature_matrix(self, params)

    def _analyze_predictors_on_holdout(self):
        fm_io = FeatureMatrixIO()

        algorithms_to_test = list()
        algorithms_to_test.extend(SupervisedClassifier.SUPPORTED_ALGORITHMS)

        pipeline_file_name = inspect.getfile(inspect.currentframe())
        data_dir = SupervisedLearningPipeline._fetch_data_dir_path(self, pipeline_file_name)
        # for algorithm in SupervisedClassifier.SUPPORTED_ALGORITHMS:
        #     algorithms_to_test.append('bifurcated-%s' % algorithm)
        log.debug('algorithms_to_test: %s' % algorithms_to_test)
        for algorithm in algorithms_to_test:
            log.info('Training and analyzing %s...' % algorithm)
            # If report_dir does not exist, make it.
            report_dir = '/'.join([data_dir, algorithm])

            pipeline_prefix = '%s-normality-prediction-%s' % (self._var, algorithm)

            predictor_path = self._build_model_dump_path(algorithm)

            if os.path.exists(predictor_path) and 'bifurcated' not in algorithm:
                log.debug('Loading model from disk...')
                # TODO(sbala): Fix loblib.load so that it works for bifurcated
                # supervised classifiers.
                self._predictor = joblib.load(predictor_path)
                # self._features = self._X_train.columns
                status = SupervisedClassifier.TRAINED

            SupervisedLearningPipeline._analyze_predictor_holdoutset(self, report_dir, pipeline_prefix)

    def _train_and_analyze_predictors(self):
        log.info('Training and analyzing predictors...')
        problem = SupervisedLearningPipeline.CLASSIFICATION
        meta_report = None
        fm_io = FeatureMatrixIO()

        # Build paths for output.
        pipeline_file_name = inspect.getfile(inspect.currentframe())
        data_dir = SupervisedLearningPipeline._fetch_data_dir_path(self, pipeline_file_name)

        # Test BifurcatedSupervisedClassifier and SupervisedClassifier.
        algorithms_to_test = list()
        algorithms_to_test.extend(SupervisedClassifier.SUPPORTED_ALGORITHMS)
        # for algorithm in SupervisedClassifier.SUPPORTED_ALGORITHMS:
        #     algorithms_to_test.append('bifurcated-%s' % algorithm)
        log.debug('algorithms_to_test: %s' % algorithms_to_test)

        # Train and analyse algorithms.
        for algorithm in algorithms_to_test:
            log.info('Training and analyzing %s...' % algorithm)
            # If report_dir does not exist, make it.
            report_dir = '/'.join([data_dir, algorithm])
            if not os.path.exists(report_dir):
                os.makedirs(report_dir)

            # Define hyperparams.
            hyperparams = {}
            hyperparams['algorithm'] = algorithm
            hyperparams['hyperparam_strategy'] = SupervisedClassifier.EXHAUSTIVE_SEARCH
            hyperparams['max_iter'] = 1024
            hyperparams['random_state'] = self._random_state

            # If bifurcated algorithm, define bifurcator.
            if 'bifurcated' in algorithm:
                # bifrucator = LAB.pre == 0
                hyperparams['bifurcator'] = '%s.pre' % self._var
                hyperparams['bifurcation_strategy'] = BifurcatedSupervisedClassifier.EQUAL
                hyperparams['bifurcation_value'] = 0
                hyperparams['bifurcated'] = True

            # Train classifier.
            predictor_path = self._build_model_dump_path(algorithm)
            if os.path.exists(predictor_path) and 'bifurcated' not in algorithm:
                log.debug('Loading model from disk...')
                # TODO(sbala): Fix loblib.load so that it works for bifurcated
                # supervised classifiers.
                self._predictor = joblib.load(predictor_path)
                self._features = self._X_train.columns
                status = SupervisedClassifier.TRAINED
            else:
                status = SupervisedLearningPipeline._train_predictor(self, problem, [0, 1], hyperparams)

            # If failed to train, write an error report.
            y_train_counts = self._y_train[self._y_train.columns[0]].value_counts()
            y_test_counts = self._y_test[self._y_test.columns[0]].value_counts()
            if status == SupervisedClassifier.INSUFFICIENT_SAMPLES:
                # Skip all analysis and reporting.
                # This will be true for all algorithms, so just return.
                # Build error report.
                algorithm_report = DataFrame(
                    {
                    'lab_panel': [self._var],
                    'algorithm': [algorithm],
                    'error': [status],
                    'y_train.value_counts()': [y_train_counts.to_dict()],
                    'y_test.value_counts()': [y_test_counts.to_dict()]
                    },
                    columns=[
                        'lab_panel', 'algorithm', 'error',
                        'y_train.value_counts()', 'y_test.value_counts()'
                    ]
                )
                header = ['LabNormalityPredictionPipeline("%s", 10000)' % self._var]
                # Write error report.
                fm_io.write_data_frame_to_file(algorithm_report, \
                    '/'.join([report_dir, '%s-normality-prediction-report.tab' % (self._var)]), \
                    header)
            # If successfully trained, append to a meta report.
            elif status == SupervisedClassifier.TRAINED:
                pipeline_prefix = '%s-normality-prediction-%s' % (self._var, algorithm)

                SupervisedLearningPipeline._analyze_predictor(self, report_dir, pipeline_prefix)
                SupervisedLearningPipeline._analyze_predictor_traindata(self, report_dir, pipeline_prefix)

                if meta_report is None:
                    meta_report = fm_io.read_file_to_data_frame('/'.join([report_dir, '%s-report.tab' % pipeline_prefix]))
                else:
                    algorithm_report = fm_io.read_file_to_data_frame('/'.join([report_dir, '%s-report.tab' % pipeline_prefix]))
                    log.debug('algorithm_report: %s' % algorithm_report)
                    meta_report = meta_report.append(algorithm_report)
                # Write predictor to disk.
                predictor = SupervisedLearningPipeline.predictor(self)
                predictor_path = self._build_model_dump_path(algorithm)
                joblib.dump(predictor, predictor_path)

        # After building per-algorithm reports, write to meta report.
        # Note that if there were insufficient samples to build any of the
        # algorithms, then meta_report will still be None.
        if meta_report is not None:
            header = ['LabNormalityPredictionPipeline("%s", 10000)' % self._var]
            fm_io.write_data_frame_to_file(meta_report, \
                '/'.join([data_dir, '%s-normality-prediction-report.tab' % self._var]), header)

TOP_LAB_PANELS_BY_CHARGE_VOLUME = set([
        "LABA1C", "LABABG", "LABBLC", "LABBLC2", "LABCAI",
        "LABCBCD", "LABCBCO", "LABHFP", "LABLAC", "LABMB",
        "LABMETB", "LABMETC", "LABMGN", "LABNTBNP", "LABPCG3",
        "LABPCTNI", "LABPHOS", "LABPOCGLU", "LABPT", "LABPTT",
        "LABROMRS", "LABTNI","LABTYPSNI", "LABUA", "LABUAPRN",
        "LABURNC", "LABVANPRL", "LABVBG"
    ])
TOP_NON_PANEL_TESTS_BY_VOLUME = set([
    "LABPT", "LABMGN", "LABPTT", "LABPHOS", "LABTNI",
    "LABBLC", "LABBLC2", "LABCAI", "LABURNC", "LABLACWB",
    "LABA1C", "LABHEPAR", "LABCDTPCR", "LABPCTNI", "LABPLTS",
    "LABLAC", "LABLIPS", "LABRESP", "LABTSH", "LABHCTX",
    "LABLDH", "LABMB", "LABK", "LABGRAM", "LABFCUL",
    "LABNTBNP", "LABCRP", "LABFLDC", "LABSPLAC", "LABANER",
    "LABCK", "LABESRP", "LABBLCTIP", "LABBLCSTK", "LABNA",
    "LABFER", "LABUSPG", "LABB12", "LABURNA", "LABFT4",
    "LABFIB", "LABURIC", "LABPALB", "LABPCCR", "LABTRFS",
    "LABUOSM", "LABAFBD", "LABSTOBGD", "LABCSFGL", "LABCSFTP",
    "LABNH3", "LABAFBC", "LABCMVQT", "LABCSFC", "LABUCR",
    "LABTRIG", "LABFE",
    # "LABNONGYN", # No base names.
    "LABALB", "LABLIDOL",
    "LABUPREG", "LABRETIC", "LABHAP", "LABBXTG", "LABHIVWBL"
])
NON_PANEL_TESTS_WITH_GT_500_ORDERS = [
    'LABA1C', 'LABAFBC', 'LABAFBD', 'LABALB', 'LABANER', 'LABB12', 'LABBLC', 'LABBLC2',
    'LABBLCSTK', 'LABBLCTIP', 'LABBUN', 'LABBXTG', 'LABCA', 'LABCAI', 'LABCDTPCR', 'LABCK',
    'LABCMVQT', 'LABCORT', 'LABCRP', 'LABCSFC', 'LABCSFGL', 'LABCSFTP', 'LABDIGL', 'LABESRP',
    'LABFCUL', 'LABFE', 'LABFER', 'LABFIB', 'LABFLDC', 'LABFOL', 'LABFT4', 'LABGRAM',
    'LABHAP', 'LABHBSAG', 'LABHCTX', 'LABHEPAR', 'LABHIVWBL', 'LABK', 'LABLAC', 'LABLACWB',
    'LABLDH', 'LABLIDOL', 'LABLIPS', 'LABMB', 'LABMGN', 'LABNA', 'LABNH3',
    # #'LABNONGYN', TODO: no components
    'LABNTBNP', 'LABOSM', 'LABPALB', 'LABPCCG4O', 'LABPCCR', 'LABPCTNI', 'LABPHOS', 'LABPLTS',
    'LABPROCT', 'LABPT', 'LABPTEG', 'LABPTT', 'LABRESP', 'LABRESPG', 'LABRETIC', 'LABSPLAC',
    'LABSTLCX', 'LABSTOBGD', 'LABTNI', 'LABTRFS', 'LABTRIG', 'LABTSH',
    # 'LABUCR', # insufficient samples
    'LABUOSM',
    'LABUA', 'LABUAPRN', 'LABUPREG', 'LABURIC',
    # 'LABURNA', # insufficient samples
    'LABURNC', 'LABUSPG'
]

STRIDE_COMPONENT_TESTS = ['WBC', 'HGB', 'PLT',
                          'NA', # TODO: Cautious, this might be identified as 'nan' by pandas
                          'K', 'CL',
                   'CR', 'BUN', 'GLU', 'CO2', 'CA',
                          'HCO3',  # good, from 'LABMETB'; TODO: Insufficient samples
                   'TP', 'ALB', 'ALKP', 'TBIL', 'AST', 'ALT',
                   'DBIL', 'IBIL', 'PHA', 'PCO2A', 'PO2A'
                          ]  # good, LABHFP

UMICH_TOP_COMPONENTS = ['WBC', 'HGB', 'PLT', 'SOD', 'POT',
                                'CREAT', 'TBIL',
                                'CHLOR', 'CO2', 'DBIL', 'AST', 'ALT',
                                'ALB', 'CAL', 'PCOAA2', 'PO2AA', 'pHA',
                                'T PROTEIN',
                                'ALK',  # ALKALINE PHOSPHATASE
                                'UN',  # Blood, Urine, 'BUN'
                                'IBIL',  # Bilirubin, Indirect
                                'HCO3-A',  # # good, from 'LABMETB'
                                'MAG',
                                'PHOS',
                                'INR',
                                "BLD", "ICAL", "LACA"
                                ]

UCSF_TOP_COMPONENTS = [
            'WBC', 'HGB', 'PLT', 'NAWB', 'K',
            'CREAT', 'TBILI',
            'CL', 'CO2', 'DBILI', 'AST', 'ALT',
            'ALB', 'CA', 'PCO2', 'PO2', 'PH37',
            'TP',
            'ALKP',
            'BUN',
            # No IBIL
            'HCO3',
            'MG',
            'PO4', #PHOSPHORUS, SERUM / PLASMA
            'INR',
            'P060', # PERIPHERAL BLOOD CULTURE
            'CAI',
            'CAIB',
            'LACTWB'
                               ]

if __name__ == '__main__':
    log.level = logging.DEBUG
    folder_debug = LocalEnv.PATH_TO_CDSS + '/scripts/LabTestAnalysis/machine_learning/data/'
    if not os.path.exists(folder_debug):
        os.mkdir(folder_debug)
    logging.basicConfig(filename=os.path.join(folder_debug,'debug_%s.log'%LocalEnv.DATASET_SOURCE_NAME), level=logging.DEBUG)

    if LocalEnv.DATASET_SOURCE_NAME == 'STRIDE':

        for panel in NON_PANEL_TESTS_WITH_GT_500_ORDERS: #['LABLAC', 'LABA1C']: #NON_PANEL_TESTS_WITH_GT_500_ORDERS:
            # LabNormalityPredictionPipeline(panel, 10000, use_cache=True, random_state=123456789, isLabPanel=True,
            #                                timeLimit=(None, '2015-12-31'), notUsePatIds=None, holdOut=False)
            used_patient_set = pickle.load(open('data/used_patient_set_%s.pkl'%panel, 'r'))
            LabNormalityPredictionPipeline(panel, 2000, use_cache=True, random_state=123456789, isLabPanel=True,
                                           timeLimit=(None, None), notUsePatIds=used_patient_set, holdOut=True)

            # try:
            #     LabNormalityPredictionPipeline(panel, 1000, use_cache=True, random_state=123456789, isLabPanel=True)
            # except ValueError:
            #     import shutil
            #     shutil.rmtree('data/%s'%panel)
            #     print 'data/%s removed!'%panel
            #     LabNormalityPredictionPipeline(panel, 10000, use_cache=True, random_state=123456789, isLabPanel=True)

        # for component in ['HGB', 'WBC', 'K', 'NA', 'CR', 'GLU' #'PLT',
        #                    ]:#STRIDE_COMPONENT_TESTS:
        #     LabNormalityPredictionPipeline(component, 10000, use_cache=True, random_state=123456789, isLabPanel=False)

    elif LocalEnv.DATASET_SOURCE_NAME == 'UMich':

        # By default, the first one should be labs
        raw_data_files = ['labs.sample.txt',
                          'pt.info.sample.txt',
                          'encounters.sample.txt',
                          'demographics.sample.txt',
                          'diagnoses.sample.txt']

        raw_data_folderpath = LocalEnv.LOCAL_PROD_DB_PARAM["DATAPATH"]
        db_name = LocalEnv.LOCAL_PROD_DB_PARAM["DSN"]
        fold_enlarge_data = 10
        USE_CACHED_DB = False # TODO: take care of USE_CACHED_LARGEFILE in the future

        prepareData_NonSTRIDE.prepare_database(raw_data_files, raw_data_folderpath,
                                               db_name=db_name,
                                               fold_enlarge_data=fold_enlarge_data,
                                               USE_CACHED_DB=USE_CACHED_DB,
                                               data_source = 'UMich')

        # for panel in UMICH_TOP_LABPANELS:
        #     LabNormalityPredictionPipeline(panel, 1000, use_cache=True, random_state=123456789, isLabPanel=True)
        for component in UMICH_TOP_COMPONENTS:
            try:
                LabNormalityPredictionPipeline(component, 10000, use_cache=False, random_state=123456789, isLabPanel=False)
            except Exception as e:
                log.info(e)
                pass

    elif LocalEnv.DATASET_SOURCE_NAME == 'UCSF':

        raw_data_folderpath = LocalEnv.LOCAL_PROD_DB_PARAM["DATAPATH"]
        db_name = LocalEnv.LOCAL_PROD_DB_PARAM["DSN"]

        # prepareData_NonSTRIDE.preprocess_files(data_source='UCSF', raw_data_folderpath=raw_data_folderpath)

        raw_data_files = ['labs.tsv',
                    'demographics_and_diagnoses.tsv',
                    'vitals.tsv'
                          ]


        fold_enlarge_data = 1
        USE_CACHED_DB = False  # TODO: take care of USE_CACHED_LARGEFILE in the future

        prepareData_NonSTRIDE.prepare_database(raw_data_files, raw_data_folderpath,
                                               db_name=db_name,
                                               fold_enlarge_data=fold_enlarge_data,
                                               USE_CACHED_DB=USE_CACHED_DB,
                                               data_source='UCSF')

        for component in UCSF_TOP_COMPONENTS:
            LabNormalityPredictionPipeline(component, 10000, use_cache=False, random_state=123456789, isLabPanel=False)
        pass

    log.info("\n"
             "Congratz, pipelining completed! \n"
             "All results and reports are stored in %s", folder_debug)




