#!/usr/bin/env python
"""
Given a set of clinical data sources output a patient episode feature matrix
for machine learning and regression applications.

Usage follows the following idiom:
factory = FeatureMatrixFactory()
factory.setFooInput()
factory.setBarInput()
...
factory.buildFeatureMatrix()
matrix = factory.getMatrixAsBaz()
"""

import csv
import datetime
import numpy as np
import os
import time

from Const import SENTINEL_RESULT_VALUE
from medinfo.common.Const import NULL_STRING
from medinfo.cpoe.Const import SECONDS_PER_DAY, DELTA_NAME_BY_DAYS
from medinfo.db import DBUtil
from medinfo.db.Model import columnFromModelList, SQLQuery, modelListFromTable
from medinfo.db.ResultsFormatter import TabDictReader, TextResultsFormatter

# For NonStanford data, we use sqlite database to allow creating database onsite
import LocalEnv
if LocalEnv.DATABASE_CONNECTOR_NAME == 'psycopg2':
    from psycopg2.extensions import cursor
elif LocalEnv.DATABASE_CONNECTOR_NAME == 'sqlite3':
    from sqlite3 import Cursor as cursor

# from Util import log
from medinfo.common.Util import log
import Util

class FeatureMatrixFactory:
    FEATURE_MATRIX_COLUMN_NAMES = [
        "patient_id"
    ]

    def __init__(self, cacheDBResults = True, PID=None):
        self.dbCache = None
        self.patientListInput = None
        self.patientIdColumn = None
        self.patientEpisodeInput = None
        self.patientEpisodeIdColumn = None
        self._patientItemTimeColumn = None
        self.timestampColumn = None

        self.patientsProcessed = None

        if not PID: # Allow checking existing tmp files
            self.PID = str(os.getpid())
        else:
            self.PID = str(PID)

        # When debugging, do not create so many Tempfiles in the working folder.
        self._folderTempFiles = "fmfTempFolder"
        if not os.path.exists(self._folderTempFiles):
            os.mkdir(self._folderTempFiles)

        self._patientListTempFileName = self._folderTempFiles + '/' + "fmf.patient_list_" + self.PID + ".tsv"
        self._patientEpisodeTempFileName = self._folderTempFiles + '/' + "fmf.patient_episodes_" + self.PID + ".tsv"
        self._patientItemTempFileNameFormat = self._folderTempFiles + '/' + "fmf.patient_%s_" + self.PID + ".tsv"
        self._patientTimeCycleTempFileNameFormat = self._folderTempFiles + '/' + "fmf.patient_%s_%s_" + self.PID + ".tsv"
        self._patientResultTempFileNameFormat = self._folderTempFiles + '/' + "fmf.patient_%s_%s_%s_" + self.PID + ".tsv"
        self._matrixFileName = None

        # Look at lab results from the previous days
        LAB_PRE_TIME_DELTAS = [
            datetime.timedelta(-1), datetime.timedelta(-3),
            datetime.timedelta(-7), datetime.timedelta(-30),
            datetime.timedelta(-90)
        ]
        # Don't look into the future, otherwise cheating the prediction
        LAB_POST_TIME_DELTA = datetime.timedelta(+0)

        self._featureTempFileNames = []
        if cacheDBResults:
            self.dbCache = dict()

    def setPatientListInput(self, patientListInput, \
        patientIdColumn = "patient_id"):
        """
        Define the input patient list for the feature matrix.
        patientListInput: TSV file descriptor or DB cursor
        patientIdColumn: Name of TSV column or DB column.
        """
        # Verify patientListInput is TSV file or DB cursor.
        if not isinstance(patientListInput, cursor) and \
            not isinstance(patientListInput, file):
            raise TypeError("patientListInput must be DB cursor or TSV file.")

        self.patientListInput = patientListInput
        self.patientIdColumn = patientIdColumn
        pass

    def processPatientListInput(self):
        """
        Convert patient list input to a TSV file.
        """
        if self.patientListInput is None:
            raise ValueError("FeatureMatrixFactory.patientListInput is None.")

        if isinstance(self.patientListInput, cursor):
            return self._processPatientListDbCursor()
        elif isinstance(self.patientListInput, file):
            return self._processPatientListTsvFile()

    def _processPatientListDbCursor(self):
        """
        Convert self.patientListInput from DB cursor to TSV file.
        """
        patientListTempFile = open(self._patientListTempFileName, "w")
        self._pipeDbCursorToTsvFile(self.patientListInput, patientListTempFile)
        patientListTempFile.close()

    def _pipeDbCursorToTsvFile(self, dbCursor, tsvFile, include_columns=True):
        """
        Pipe any arbitrary DB cursor to a TSV file.
        """
        # Extract DB columns.
        columns = dbCursor.description
        numColumns = len(columns)

        if include_columns:
            # Write TSV header.
            for i in range(numColumns - 1):
                # 0th index is column name.
                tsvFile.write("%s\t" % columns[i][0])
            tsvFile.write("%s\n" % columns[numColumns - 1][0])

        # By default, cursor iterates through both header and data rows.
        self._numRows = 0
        row = dbCursor.fetchone()
        while row is not None:
            for i in range(numColumns - 1):
                tsvFile.write("%s\t" % row[i])
            tsvFile.write("%s\n" % row[numColumns - 1])
            row = dbCursor.fetchone()
            self._numRows += 1

    def _processPatientListTsvFile(self):
        """
        Convert self.patientListInput from DB cursor to TSV file.
        """
        # Instantiate patientListTempFile.
        patientListTempFile = open(self._patientListTempFileName, "w")
        patientListTempFile.write("%s\n" % self.patientIdColumn)

        # Iterate through all rows in TSV file.
        # Extract patientId from dictionary.
        for row in TabDictReader(self.patientListInput):
            patientId = int(row[self.patientIdColumn])
            patientListTempFile.write("%s\n" % patientId)

        patientListTempFile.close()

    def getPatientListIterator(self):
        """
        Return TabDictReader for reading processed patient list.
        """
        return TabDictReader(open(self._patientListTempFileName, "r"))

    def setPatientEpisodeInput(self, patientEpisodeInput, \
        patientIdColumn = "patient_id", timestampColumn = "item_date"):
        """
        Define the input patient episode list for the feature matrix.
        patientEpisodeInput: TSV file descriptor or DB cursor.
        patientIdColumn: Name of TSV column or DB column.
        timestampColumn: Name of TSV column or DB column.
        """
        # Verify patientEpisodeInput is TSV file or DB cursor.
        if not isinstance(patientEpisodeInput, cursor) and \
            not isinstance(patientEpisodeInput, file):
            raise TypeError("patientEpisodeInput must be DB cursor or TSV file.")

        self.patientEpisodeInput = patientEpisodeInput
        self.patientEpisodeIdColumn = patientIdColumn
        self.patientEpisodeTimeColumn = timestampColumn

    def processPatientEpisodeInput(self):
        """
        Convert patient episode input to a TSV file.
        """
        if self.patientEpisodeInput is None:
            raise ValueError("FeatureMatrixFactory.patientEpisodeInput is None.")

        if isinstance(self.patientEpisodeInput, cursor):
            return self._processPatientEpisodeDbCursor()
        elif isinstance(self.patientEpisodeInput, file):
            return self._processPatientEpisodeTsvFile()

    def _processPatientEpisodeDbCursor(self):
        """
        Convert self.patientEpisodeInput from DB cursor to TSV file.
        """
        # Instantiate patientEpisodeTempFile.
        patientEpisodeTempFile = open(self._patientEpisodeTempFileName, "w")
        self._pipeDbCursorToTsvFile(self.patientEpisodeInput, patientEpisodeTempFile)
        patientEpisodeTempFile.close()
        self.patientsProcessed = True

        if LocalEnv.DATABASE_CONNECTOR_NAME == 'psycopg2':
            return self.patientEpisodeInput.rowcount
        elif LocalEnv.DATABASE_CONNECTOR_NAME == 'sqlite3':
        # In sqlite3, rowcount is somehow "always" -1; See for details:
        # https://docs.python.org/3.0/library/sqlite3.html#sqlite3.Cursor.rowcount
            return self._numRows #self.patientEpisodeInput.rowcount

    def _processPatientEpisodeTsvFile(self):
        pass

    def getPatientEpisodeIterator(self):
        """
        Return TabDictReader for reading processed patient episodes.
        """
        return TabDictReader(open(self._patientEpisodeTempFileName, "r"))

    '''
    New version, adapt to the new split_by_patient pipeline
    '''
    def obtain_baseline_results(self, raw_matrix_path, random_state, isLabPanel=True, isHoldOut=False):
        from medinfo.dataconversion.FeatureMatrixIO import FeatureMatrixIO
        fm_io = FeatureMatrixIO()

        processed_matrix_path = raw_matrix_path.replace('-raw','-processed')

        '''
        get prevalence from the train set
        '''
        processed_matrix_train = fm_io.read_file_to_data_frame(processed_matrix_path.replace('-matrix', '-train-matrix'))
        if isLabPanel:
            y_label = 'all_components_normal'
        else:
            y_label = 'component_normal'

        prevalence = float(processed_matrix_train[y_label].values.sum())/float(processed_matrix_train.shape[0])

        '''
        '''
        processed_matrix_test = fm_io.read_file_to_data_frame(processed_matrix_path.replace('-matrix', '-test-matrix'))
        pats_test = set(processed_matrix_test['pat_id'].values.tolist())
        raw_matrix = fm_io.read_file_to_data_frame(raw_matrix_path)
        raw_matrix_test = raw_matrix[raw_matrix['pat_id'].isin(pats_test)]
        raw_matrix_test = raw_matrix_test.sort_values(['pat_id', 'order_time']).reset_index()
        raw_matrix_test['predict_proba'] = raw_matrix_test[y_label].apply(lambda x: prevalence)

        for i in range(1, raw_matrix_test.shape[0]):
            if raw_matrix_test.ix[i - 1, 'pat_id'] == raw_matrix_test.ix[i, 'pat_id']:
                raw_matrix_test.ix[i, 'predict_proba'] = raw_matrix_test.ix[i - 1, y_label]

        baseline_comparisons = raw_matrix_test[['predict_proba', y_label]]
        baseline_comparisons = baseline_comparisons.rename(columns={y_label:'actual',
                                                            'predict_proba':'predict'})

        baseline_folder = '/'.join(raw_matrix_path.split('/')[:-1])
        baseline_filepath = os.path.join(baseline_folder, 'baseline_comparisons.csv')
        # os.rename(baseline_filepath, baseline_filepath.replace('baseline_comparisons', 'baseline_comparisons_prev')) # existing ones
        baseline_comparisons.to_csv(baseline_filepath)


    '''
    Old version, compatible to the previous split_by_episode pipeline
    '''
    def obtain_baseline_results_(self, raw_matrix_path, random_state, isLabPanel=True, isHoldOut=False):
        # Step1: group by pat_id
        # Step2: For each group, obtain predicts
        #   Step 2.1: order by order_time
        #   Step 2.2: Obtain

        import pandas as pd
        pd.set_option('display.width', 300)
        pd.set_option('display.max_column', 10)

        from medinfo.dataconversion.FeatureMatrixIO import FeatureMatrixIO
        fm_io = FeatureMatrixIO()
        raw_matrix = fm_io.read_file_to_data_frame(raw_matrix_path)

        episode_cnt = raw_matrix.shape[0]

        if isLabPanel:
            ylabel = 'all_components_normal'
        else:
            ylabel = 'component_normal'

        raw_matrix_dict = raw_matrix[['pat_id', 'order_time', ylabel]].to_dict('records')

        X = range(episode_cnt)
        from sklearn.model_selection import train_test_split
        X_train, X_test = train_test_split(X, random_state=random_state) #

        actual_cnt_1 = 0
        actual_cnt_0 = 0

        episode_groups_dict = {}
        episode_ind = 0
        for episode_dict in raw_matrix_dict:
            if episode_ind in X_test:
                if episode_dict['pat_id'] in episode_groups_dict:
                    episode_groups_dict[episode_dict['pat_id']].append(episode_dict)
                else:
                    episode_groups_dict[episode_dict['pat_id']] = [episode_dict]
            else:
                if int(episode_dict[ylabel]) == 1:
                    actual_cnt_1 += 1
                else:
                    actual_cnt_0 += 1
            episode_ind += 1

        # Calc the prevalence from training data
        prevalence_1 = float(actual_cnt_1)/float(actual_cnt_1+actual_cnt_0)

        baseline_comparisons = pd.DataFrame(columns=['actual', 'predict'])

        for pat_id in episode_groups_dict:
            #   Step 2.1: order by order_time
            newlist = sorted(episode_groups_dict[pat_id], key=lambda k: k['order_time'])

            newlist[0]['predict'] = prevalence_1
            baseline_comparisons = baseline_comparisons.append({'actual':newlist[0][ylabel],
                                         'predict':newlist[0]['predict']}, ignore_index=True)

            for i in range(1,len(newlist)):
                newlist[i]['predict'] = newlist[i-1][ylabel]
                baseline_comparisons = baseline_comparisons.append({'actual': newlist[i][ylabel],
                                             'predict': newlist[i]['predict']}, ignore_index=True)

        baseline_folder = '/'.join(raw_matrix_path.split('/')[:-1])

        if not isHoldOut:
            baseline_comparisons.to_csv(os.path.join(baseline_folder, 'baseline_comparisons.csv'))
        else:
            baseline_comparisons.to_csv(os.path.join(baseline_folder, 'baseline_comparisons_holdout.csv'))

    def _getPatientEpisodeByIndexTimeById(self):
        """
        Return dictionary containing patientId : episodeTime : {} map.
        """
        patientEpisodeByIndexTimeById = {}
        patientEpisodeIterator = self.getPatientEpisodeIterator()

        for episode in patientEpisodeIterator:
            patientId = int(episode[self.patientEpisodeIdColumn])
            episodeTime = DBUtil.parseDateValue(episode[self.patientEpisodeTimeColumn])

            if patientId not in patientEpisodeByIndexTimeById:
                patientEpisodeByIndexTimeById[patientId] = {episodeTime: {}}
            elif episodeTime not in patientEpisodeByIndexTimeById[patientId]:
                patientEpisodeByIndexTimeById[patientId][episodeTime] = {}

        return patientEpisodeByIndexTimeById

    def addClinicalItemFeatures(self, clinicalItemNames, dayBins=None, column=None, operator=None, label=None, features=None, isLabPanel=True):
        """
        Query patient_item for the clinical item orders and results for each
        patient, and aggregate by episode timestamp.
        column: determines column in clinical_item to match clinicalItemNames.
        operator: determines how to match clinicalItemNames against column.
        label: sets the column prefix in the final feature matrix.
        features: determines whether to include "pre", "post" or "all".
        """
        # Verify patient list and/or patient episode has been processed.
        if not self.patientsProcessed:
            raise ValueError("Must process patients before clinical item.")

        if isLabPanel:
            clinicalItemEvents = self._queryClinicalItemsByName(clinicalItemNames, column=column, operator=operator)
        else:
            clinicalItemEvents = self._queryComponentItemsByName(clinicalItemNames)
        itemTimesByPatientId = self._getItemTimesByPatientId(clinicalItemEvents)

        # Read clinical item features to temp file.
        patientEpisodes = self.getPatientEpisodeIterator()
        self._processClinicalItemEvents(patientEpisodes, itemTimesByPatientId, \
                                        clinicalItemNames, dayBins, label=label, features=features)

    # Updated this core function for Component and Non-Stanford data. Responsible for creating features of:
    # lab_panel, component (for counting "order times"), birth/death, sex, race, comorbidity
    def addClinicalItemFeatures_NonStanford(self, clinicalItemNames, dayBins=None, label=None, features=None
                                , clinicalItemType=None, clinicalItemTime=None, tableName=None):
        """
        Query patient_item for the clinical item orders and results for each
        patient, and aggregate by episode timestamp.
        column: determines column in clinical_item to match clinicalItemNames.
        operator: determines how to match clinicalItemNames against column.
        label: sets the column prefix in the final feature matrix.
        features: determines whether to include "pre", "post" or "all".
        """
        # Verify patient list and/or patient episode has been processed.
        if not self.patientsProcessed:
            raise ValueError("Must process patients before clinical item.")

        # For adapting to NonStanford data, instead of creating intermediate tables clinical_items
        # and patient_items, we directly query "raw" tables from the NonStanford.db
        clinicalItemEvents = self._queryNonStanfordItemsByName(clinicalItemNames=clinicalItemNames, clinicalItemType=clinicalItemType,
                                                            tableName=tableName, clinicalItemTime=clinicalItemTime)
        itemTimesByPatientId = self._getItemTimesByPatientId(clinicalItemEvents)

        # Read clinical item features to temp file.
        patientEpisodes = self.getPatientEpisodeIterator()
        self._processClinicalItemEvents(patientEpisodes, itemTimesByPatientId, \
                                        clinicalItemNames, dayBins, label=label, features=features)

    def addClinicalItemFeaturesByCategory(self, categoryIds, label=None, dayBins=None, features=None):
        """
        Query patient_item for the clinical item orders and results for each
        patient (based on clinical item category ID instead of item name), and
        aggregate by episode timestamp.
        features: determines whether to include "pre", "post" or "all".
        """
        # Verify patient list and/or patient episode has been processed.
        if not self.patientsProcessed:
            raise ValueError("Must process patients before clinical item.")

        if label is None:
            label = "-".join(categoryIds)

        clinicalItemEvents = self._queryClinicalItemsByCategory(categoryIds)
        itemTimesByPatientId = self._getItemTimesByPatientId(clinicalItemEvents)

        # Read clinical item features to temp file.
        patientEpisodes = self.getPatientEpisodeIterator()
        self._processClinicalItemEvents(patientEpisodes, itemTimesByPatientId, \
                                        categoryIds, dayBins, label=label, features=features)

    # This function is only used for handling the feature of AdmitDxDate
    def addClinicalItemFeaturesByCategory_NonStanford(self, categoryIds, label=None, dayBins=None, features=None,
                                          tableName=None):
        """
        Query patient_item for the clinical item orders and results for each
        patient (based on clinical item category ID instead of item name), and
        aggregate by episode timestamp.
        features: determines whether to include "pre", "post" or "all".
        """
        # Verify patient list and/or patient episode has been processed.
        if not self.patientsProcessed:
            raise ValueError("Must process patients before clinical item.")

        if label is None:
            label = "-".join(categoryIds)

        # For NonStanford data, directly query label='AdmitDxDate' from the raw table
        clinicalItemEvents = self._queryNonStanfordItemsByCategory(label,tableName) #
        itemTimesByPatientId = self._getItemTimesByPatientId(clinicalItemEvents)

        # Read clinical item features to temp file.
        patientEpisodes = self.getPatientEpisodeIterator()
        self._processClinicalItemEvents(patientEpisodes, itemTimesByPatientId, \
                                        categoryIds, dayBins, label=label, features=features)

    def _queryClinicalItemsByName(self, clinicalItemNames, column=None, operator=None):
        """
        Query clinicalItemInput for all item times for all patients.

        Look for clinical items by name.
        Will match by SQL "LIKE" so can use wild-cards,
        or can use ~* operator for additional regular expression matching.
        """
        # Verify patient list and/or patient episode has been processed.
        if not self.patientsProcessed:
            raise ValueError("Must process patients before clinical item.")

        clinicalItemIds = None

        # If possible, return cached results.
        cacheKey = str(clinicalItemNames)
        if self.dbCache is not None and cacheKey in self.dbCache:
            clinicalItemIds = self.dbCache[cacheKey]
        else:
            if column is None:
                column = "name"
            if operator is None:
                operator = "LIKE"

            query = SQLQuery()
            query.addSelect("clinical_item_id")
            query.addFrom("clinical_item")

            nameClauses = list()
            for itemName in clinicalItemNames:
                if LocalEnv.DATABASE_CONNECTOR_NAME == 'psycopg2':
                    nameClauses.append("%s %s %%s" % (column, operator))

                elif LocalEnv.DATABASE_CONNECTOR_NAME == 'sqlite3':
                    # For postgres, placeholder is %s
                    # For sqlite, place holder is ?
                    # TODO: %s or %%s for postgres
                    # nameClauses.append("%s %s %%s" % (column, operator))
                    nameClauses.append("%s %s " % (column, operator) + DBUtil.SQL_PLACEHOLDER) #
                query.params.append(itemName)
            query.addWhere(str.join(" or ", nameClauses))

            results = DBUtil.execute(query)
            clinicalItemIds = [row[0] for row in results]

        if len(clinicalItemIds) == 0:
            return list()

        return self.queryClinicalItems(clinicalItemIds)

    def _queryMichiganItemsByName(self, clinicalItemNames, clinicalItemType, tableName, clinicalItemTime):
        # """
        # Query ComponentItemInput for all item times for all patients.
        #
        # Done by directly querying the stride_order_XXX tables,
        # without using pre-assembled tables like clinical_item.
        # Might do this in the future to boost efficiency.
        # """
        patientIds = set()
        patientEpisodes = self.getPatientEpisodeIterator()
        for episode in patientEpisodes:
            patientIds.add(episode[self.patientEpisodeIdColumn])

        # clinicalItemNames can be specific examples like CBCD, anything, male,
        # clinicalItemCategory can be column names like proc_code, birth, sex,
        # clinicalItemTime can be column names like order_time, birth, birth ...

        query_str = "SELECT CAST(pat_id AS BIGINT) AS pat_id "
        if clinicalItemTime:
            query_str += ", %s " % clinicalItemTime

        query_str += "FROM %s " % tableName

        if clinicalItemType:
            query_str += "WHERE %s IN (" % (clinicalItemType)
            for clinicalItemName in clinicalItemNames:
                query_str += '"%s",' % clinicalItemName
            query_str = query_str[:-1] + ") AND "
        else:
            query_str += "WHERE "

        query_str += "pat_id IN "
        pat_list_str = "("
        for pat_id in patientIds:
            pat_list_str += str(pat_id) + ","
        pat_list_str = pat_list_str[:-1] + ") "
        query_str += pat_list_str
        query_str += "GROUP BY pat_id "
        if clinicalItemTime:
            query_str += ", %s " % clinicalItemTime

        query_str += "ORDER BY pat_id "
        if clinicalItemTime:
            query_str += ", %s " % clinicalItemTime

        _cursor = DBUtil.connection().cursor()
        _cursor.execute(query_str)
        results = _cursor.fetchall()

        componentItemEvents = [list(row) for row in results]
        if not clinicalItemTime:
            componentItemEvents = [x + [datetime.datetime(1900, 1, 1)] for x in componentItemEvents]

        return componentItemEvents


    def _queryComponentItemsByName(self, clinicalItemNames): # sx
        # """
        # Query ComponentItemInput for all item times for all patients.
        #
        # Done by directly querying the stride_order_XXX tables,
        # without using pre-assembled tables like clinical_item.
        # Might do this in the future to boost efficiency.
        # """

        query = SQLQuery()
        query.addSelect('CAST(pat_id AS BIGINT) AS pat_id')
        query.addSelect('order_time')
        query.addFrom('stride_order_proc AS sop')
        query.addFrom('stride_order_results AS sor')
        query.addWhere('sop.order_proc_id = sor.order_proc_id')
        query.addWhereIn("base_name", clinicalItemNames)
        query.addGroupBy('pat_id')
        query.addGroupBy('order_time')
        query.addOrderBy('pat_id')
        query.addOrderBy('order_time')

        results = DBUtil.execute(query)
        componentItemEvents = [row for row in results]
        return componentItemEvents

    def _queryMichiganItemsByCategory(self, label, tableName): #
        """
        Query for all patient items that match with the given clinical item
        category ID.
        """
        # Identify which columns to pull from patient_item table.

        # return sth like
        # clinicalItemEvents=[[-3384542270496665494, u'2009-07-07 13:00:00'], [1262980084096039344, u'2003-01-22 12:29:00'], ...]
        self._patientItemIdColumn = "pat_id"
        self._patientItemTimeColumn = label

        patientIds = set()
        patientEpisodes = self.getPatientEpisodeIterator()
        for episode in patientEpisodes:
            patientIds.add(episode[self.patientEpisodeIdColumn])

        query_str = "SELECT %s, %s " % (self._patientItemIdColumn, self._patientItemTimeColumn)

        query_str += " FROM %s " % tableName

        query_str += "WHERE pat_id IN "
        pat_list_str = "("
        for pat_id in patientIds:
            pat_list_str += str(pat_id) + ","
        pat_list_str = pat_list_str[:-1] + ") "
        query_str += pat_list_str

        query_str += "ORDER BY pat_id, %s " % label

        results = DBUtil.connection().cursor().execute(query_str).fetchall()

        clinicalItemEvents = [list(row) for row in results]
        return clinicalItemEvents


    def _queryClinicalItemsByCategory(self, categoryIds):
        """
        Query for all patient items that match with the given clinical item
        category ID.
        """
        # Identify which columns to pull from patient_item table.
        self._patientItemIdColumn = "patient_id"
        self._patientItemTimeColumn = "item_date"

        clinicalItemIds = None

        # If possible, return cached results.
        cacheKey = str(categoryIds)
        if self.dbCache is not None and cacheKey in self.dbCache:
            clinicalItemIds = self.dbCache[cacheKey]
        else:
            column = "clinical_item_category_id"

            query = SQLQuery()
            query.addSelect("clinical_item_id")
            query.addFrom("clinical_item")
            query.addWhereIn(column, categoryIds)

            results = DBUtil.execute(query)
            clinicalItemIds = [row[0] for row in results]

        if len(clinicalItemIds) == 0:
            return list()

        return self.queryClinicalItems(clinicalItemIds)

    def queryClinicalItems(self, clinicalItemIds):
        """
        Query for all patient items that match with the given clinical item IDs.
        """
        # Identify which columns to pull from patient_item table.
        self._patientItemIdColumn = "patient_id"
        self._patientItemTimeColumn = "item_date"

        # Identify which patients to query.
        patientIds = set()
        patientEpisodes = self.getPatientEpisodeIterator()
        for episode in patientEpisodes:
            patientIds.add(episode[self.patientEpisodeIdColumn])

        # Construct query to pull from patient_item table.
        query = SQLQuery()
        query.addSelect(self._patientItemIdColumn)
        query.addSelect(self._patientItemTimeColumn)
        query.addFrom("patient_item")
        query.addWhereIn("clinical_item_id", clinicalItemIds)
        query.addWhereIn("patient_id", list(patientIds))
        query.addOrderBy("patient_id")
        query.addOrderBy("item_date")

        # Query clinical items.
        results = DBUtil.execute(query)
        clinicalItemEvents = [row for row in results]
        return clinicalItemEvents

    def _processClinicalItemEvents(self, patientEpisodes, itemTimesByPatientId, clinicalItemNames, dayBins, label=None, features=None):
        """
        Convert temp file containing all (patient_item, item_date) pairs
        for a given set of clinical_item_ids into temp file containing
        patient_id, order_time, clinical_item.pre, clinical_item.post, etc.
        features: determines whether to include "pre", "post" or "all".
        """
        if label:
            itemLabel = label
        else:
            if len(clinicalItemNames) > 1:
                itemLabel = "-".join([itemName for itemName in clinicalItemNames])
            else:
                itemLabel = clinicalItemNames[0]
        tempFileName = self._patientItemTempFileNameFormat % itemLabel
        tempFile = open(tempFileName, "w")

        if features is None:
            features = "all"

        # Determine time buckets for clinical item times.
        if dayBins is None:
            dayBins = DELTA_NAME_BY_DAYS.keys()
            dayBins.sort()

        # Find items most proximate before and after the index item per patient
        # Record timedelta separating nearest items found from index item
        # Count up total items found before, after, and within days time bins
        preTimeDaysLabel = "%s.preTimeDays" % itemLabel
        postTimeDaysLabel = "%s.postTimeDays" % itemLabel
        preLabel = "%s.pre" % itemLabel
        postLabel = "%s.post" % itemLabel

        # Write header fields to tempFile.
        tempFile.write("patient_id\tepisode_time")
        # Include counts for events before episode_time.
        if features != "post":
            tempFile.write("\t%s" % preTimeDaysLabel)
            tempFile.write("\t%s" % preLabel)
            if len(dayBins) > 0:
                tempFile.write("\t")
                tempFile.write("\t".join("%s.%dd" % (preLabel, dayBin) for dayBin in dayBins))
        # Include counts for events after episode_time.
        if features != "pre":
            tempFile.write("\t%s" % postTimeDaysLabel)
            tempFile.write("\t%s" % postLabel)
            if len(dayBins) > 0:
                tempFile.write("\t")
                tempFile.write("\t".join("%s.%dd" % (postLabel, dayBin) for dayBin in dayBins))
        tempFile.write("\n")

        # Write patient episode data to tempFile.
        for patientEpisode in patientEpisodes:
            # Initialize data to write to tempFile for patientEpisode.
            episodeData = {}
            patientId = int(patientEpisode[self.patientEpisodeIdColumn])
            episodeTime = DBUtil.parseDateValue(patientEpisode[self.patientEpisodeTimeColumn])
            # Time delta between index time and most closest past item event.
            episodeData[preTimeDaysLabel] = None
            # Time delta between index time and most closest future item event.
            episodeData[postTimeDaysLabel] = None
            # Number of item events before index time.
            episodeData[preLabel] = 0
            # Number of item events after index time.
            episodeData[postLabel] = 0
            # Number of item events within dayBin.
            for dayBin in dayBins:
                episodeData["%s.%dd" % (preLabel, dayBin)] = 0
                episodeData["%s.%dd" % (postLabel, dayBin)] = 0

            # Aggregate item events by day buckets.
            if patientId in itemTimesByPatientId:
                itemTimes = itemTimesByPatientId[patientId]
                if itemTimes is not None:
                    for itemTime in itemTimes:
                        # Need this extra check because if a given event
                        # has not occurred yet, but will occur, itemTime will
                        # be none while itemTimes is not None.
                        if (itemTime is None) or (not isinstance(itemTime, datetime.datetime)):
                            continue
                        timeDiffSeconds = (itemTime - episodeTime).total_seconds()
                        timeDiffDays = timeDiffSeconds / SECONDS_PER_DAY
                        # If event occurred before index time...
                        if timeDiffDays < 0:
                            if episodeData[preTimeDaysLabel] is None:
                                episodeData[preTimeDaysLabel] = timeDiffDays
                            elif abs(timeDiffDays) < abs(episodeData[preTimeDaysLabel]):
                                # Found more recent item event
                                episodeData[preTimeDaysLabel] = timeDiffDays
                            episodeData[preLabel] += 1
                            for dayBin in dayBins:
                                if abs(timeDiffDays) <= dayBin:
                                    episodeData["%s.%dd" % (preLabel, dayBin)] += 1
                        # Event occurred after index time...
                        else:
                            if episodeData[postTimeDaysLabel] is None:
                                episodeData[postTimeDaysLabel] = timeDiffDays
                            elif abs(timeDiffDays) < abs(episodeData[postTimeDaysLabel]):
                                # Found more proximate future event
                                episodeData[postTimeDaysLabel] = timeDiffDays
                            episodeData[postLabel] += 1
                            for dayBin in dayBins:
                                if abs(timeDiffDays) <= dayBin:
                                    episodeData["%s.%dd" % (postLabel, dayBin)] += 1

            # Write data to tempFile.
            tempFile.write("%s\t%s" % (patientId, episodeTime))
            # Include counts for events before episode_time.
            if features != "post":
                tempFile.write("\t%s" % episodeData[preTimeDaysLabel])
                tempFile.write("\t%s" % episodeData[preLabel])
                if len(dayBins) > 0:
                    tempFile.write("\t")
                    tempFile.write("\t".join([str(episodeData["%s.%dd" % (preLabel, dayBin)]) for dayBin in dayBins]))
            # Include counts for events after episode_time.
            if features != "pre":
                tempFile.write("\t%s" % episodeData[postTimeDaysLabel])
                tempFile.write("\t%s" % episodeData[postLabel])
                if len(dayBins) > 0:
                    tempFile.write("\t")
                    tempFile.write("\t".join([str(episodeData["%s.%dd" % (postLabel, dayBin)]) for dayBin in dayBins]))
            tempFile.write("\n")

        tempFile.close()
        # Add tempFileName to list of feature temp files.
        self._featureTempFileNames.append(tempFileName)

    def addLabResultFeatures(self, labNames, labIsPanel = True, preTimeDelta = None, postTimeDelta = None):
        """
        Query stride_order_proc and stride_order_results for the lab orders and
        results for each patient, and aggregate by episode timestamp.
        Set labIsPanel = False to signify that the labNames are components,
        rather than panels.
        """
        # Verify patient list and/or patient episode has been processed.
        if not self.patientsProcessed:
            raise ValueError("Must process patients before lab result.")

        # Open temp file.
        # For multi-component labels, the first element becomes None
        labNames = [x for x in labNames if x is not None]

        if len(labNames) > 1:
            resultLabel = "-".join([labName for labName in labNames])[:64]
        else:
            resultLabel = labNames[0]

        # Hack to account for fact that Windows filenames can't include ':'.
        tempFileName = self._patientResultTempFileNameFormat % (resultLabel, str(preTimeDelta.days), str(postTimeDelta.days))
        tempFile = open(tempFileName, "w")

        # Query lab results for the individuals of interest.
        labResults = self._queryLabResultsByName(labNames, labIsPanel)
        resultsByNameByPatientId = self._parseResultsData(labResults, "pat_id",
            "base_name", "ord_num_value", "result_time")

        # Define how far in advance of each episode to look at lab results.
        preTimeDays = None
        if preTimeDelta is not None:
            preTimeDays = preTimeDelta.days
        postTimeDays = None
        if postTimeDelta is not None:
            postTimeDays = postTimeDelta.days

        # Add summary features to patient-time instances.
        patientEpisodeByIndexTimeById = self._getPatientEpisodeByIndexTimeById()
        self._processResultEvents(patientEpisodeByIndexTimeById,
                                    resultsByNameByPatientId,
                                    labNames,
                                    "ord_num_value",
                                    "result_time",
                                    preTimeDelta,
                                    postTimeDelta)

        # Write column headers to temp file.
        tempFile.write("%s\t%s\t" % (self.patientEpisodeIdColumn, self.patientEpisodeTimeColumn))
        columnNames = self.colsFromBaseNames(labNames, preTimeDays, postTimeDays)
        tempFile.write("\t".join(columnNames))
        tempFile.write("\n")

        #Write actual patient episode data to temp file.
        patientEpisodes = self.getPatientEpisodeIterator()
        for episode in patientEpisodes:
            patientId = int(episode[self.patientEpisodeIdColumn])
            indexTime = DBUtil.parseDateValue(episode[self.patientEpisodeTimeColumn])
            episodeLabData = patientEpisodeByIndexTimeById[patientId][indexTime]
            tempFile.write("%s\t%s\t" % (patientId, indexTime))
            # Need to generate columnNames again because colsFromBaseNames
            # returns generator, which can only be read once.
            columnNames = self.colsFromBaseNames(labNames, preTimeDays, postTimeDays)
            tempFile.write("\t".join(str(episodeLabData[columnName]) for columnName in columnNames))
            tempFile.write("\n")

        tempFile.close()
        # Add tempFileName to list of feature temp files.
        self._featureTempFileNames.append(tempFileName)

        return

    def addFlowsheetFeatures(self, flowsheetBaseNames, preTimeDelta = None, postTimeDelta = None):
        """
        Query stride_flowsheet for each patient, and aggregate by episode.
        """
        # Verify patient list and/or patient episode has been processed.
        if not self.patientsProcessed:
            raise ValueError("Must process patients before lab result.")

        # Open temp file.
        if len(flowsheetBaseNames) > 1:
            resultLabel = "-".join([baseName for baseName in flowsheetBaseNames])
        else:
            resultLabel = flowsheetBaseNames[0]
        # Hack to account for fact that Windows filenames can't include ':'.
        tempFileName = self._patientResultTempFileNameFormat % (resultLabel, str(preTimeDelta.days), str(postTimeDelta.days))
        tempFile = open(tempFileName, "w")

        # Query flowsheet results.
        flowsheetResults = self._queryFlowsheetResultsByName(flowsheetBaseNames)
        resultsByNameByPatientId = self._parseResultsData(flowsheetResults, \
            "pat_id", "flowsheet_name", "flowsheet_value", \
            "shifted_dt_tm")

        # Define how far in advance of each episode to look at lab results.
        preTimeDays = None
        if preTimeDelta is not None:
            preTimeDays = preTimeDelta.days
        postTimeDays = None
        if postTimeDelta is not None:
            postTimeDays = postTimeDelta.days

        # Add summary features to patient-time instances.
        patientEpisodeByIndexTimeById = self._getPatientEpisodeByIndexTimeById()
        self._processResultEvents(patientEpisodeByIndexTimeById,
                                    resultsByNameByPatientId,
                                    flowsheetBaseNames,
                                    "flowsheet_value",
                                    "shifted_dt_tm",
                                    preTimeDelta,
                                    postTimeDelta)

        # Write column headers to temp file.
        tempFile.write("%s\t%s\t" % (self.patientEpisodeIdColumn, self.patientEpisodeTimeColumn))
        columnNames = self.colsFromBaseNames(flowsheetBaseNames, preTimeDays, postTimeDays)
        tempFile.write("\t".join(columnNames))
        tempFile.write("\n")

        #Write actual patient episode data to temp file.
        patientEpisodes = self.getPatientEpisodeIterator()
        for episode in patientEpisodes:
            patientId = int(episode[self.patientEpisodeIdColumn])
            indexTime = DBUtil.parseDateValue(episode[self.patientEpisodeTimeColumn])
            episodeLabData = patientEpisodeByIndexTimeById[patientId][indexTime]
            tempFile.write("%s\t%s\t" % (patientId, indexTime))
            # Need to generate columnNames again because colsFromBaseNames
            # returns generator, which can only be read once.
            columnNames = self.colsFromBaseNames(flowsheetBaseNames, preTimeDays, postTimeDays)
            tempFile.write("\t".join(str(episodeLabData[columnName]) for columnName in columnNames))
            tempFile.write("\n")

        tempFile.close()
        # Add tempFileName to list of feature temp files.
        self._featureTempFileNames.append(tempFileName)

        return

    def _queryFlowsheetResultsByName(self, flowsheetBaseNames):
        """
        Query stride_flowsheet for each patient.
        """
        # Verify patient list and/or patient episode has been processed.
        if not self.patientsProcessed:
            raise ValueError("Must process patients before lab results.")

        # Identify which patients to query.
        patientIds = set()
        patientEpisodes = self.getPatientEpisodeIterator()
        for episode in patientEpisodes:
            patientIds.add(episode[self.patientEpisodeIdColumn])

        # Build SQL query.
        if LocalEnv.DATASET_SOURCE_NAME == 'STRIDE':
            pat_col = "pat_anon_id"
        elif LocalEnv.DATASET_SOURCE_NAME == 'UCSF':
            pat_col = "pat_id"

        colNames = ["%s AS pat_id"%pat_col, "flo_meas_id", "flowsheet_name", \
            "flowsheet_value", "shifted_dt_tm"]
        # query = SQLQuery()
        # for col in colNames:
        #     query.addSelect(col)
        # if LocalEnv.DATASET_SOURCE_NAME == 'STRIDE':
        #     query.addFrom("stride_flowsheet")
        # elif LocalEnv.DATASET_SOURCE_NAME == 'UCSF':
        #     query.addFrom("vitals")
        # query.addWhereIn("flowsheet_name", flowsheetBaseNames)
        # query.addWhereIn(pat_col, patientIds)
        # query.addOrderBy(pat_col)
        # query.addOrderBy("shifted_dt_tm")

        query_str = "SELECT "
        for colName in colNames:
            query_str += colName + ','
        query_str = query_str[:-1]

        if LocalEnv.DATASET_SOURCE_NAME == 'STRIDE':
            query_str += " FROM stride_flowsheet "
        elif LocalEnv.DATASET_SOURCE_NAME == 'UCSF':
            query_str += " FROM vitals "
        query_str += " WHERE flowsheet_name IN ("
        for flowsheetBaseName in flowsheetBaseNames:
            query_str += "'" + flowsheetBaseName + "',"
        query_str = query_str[:-1] + ')'

        query_str += " AND %s IN (" % pat_col

        for patientId in patientIds:
            query_str += patientId + ','
        query_str = query_str[:-1] + ')'

        query_str += " ORDER BY %s, shifted_dt_tm" % pat_col

        # print query_str
        log.debug(query_str)

        # results = DBUtil.connection().cursor().execute(query_str).fetchall()
        # print results
        cur = DBUtil.connection().cursor()
        cur.execute(query_str)

        results = []
        colNames = DBUtil.columnNamesFromCursor(cur)
        results.append(colNames)

        dataTable = list(cur.fetchall())
        for i, row in enumerate(dataTable):
            dataTable[i] = list(row);
        results.extend(dataTable);

        # Execute query.
        # return modelListFromTable(DBUtil.execute(query, includeColumnNames=True))
        return modelListFromTable(results)

    def colsFromBaseNames(self, baseNames, preTimeDays, postTimeDays):
        """Enumerate derived column/feature names given a set of (lab) result base names"""
        suffixes = ["count","countInRange","min","max","median","mean","std","first","last","diff","slope","proximate","firstTimeDays","lastTimeDays","proximateTimeDays"]
        colNames = list()
        for baseName in baseNames:
            for suffix in suffixes:
                colName = "%s.%s_%s.%s" % (baseName, preTimeDays, postTimeDays, suffix)
                colNames.extend([colName])

        return colNames

    def _processResultEvents(self, patientEpisodeByIndexTimeById, resultsByNameByPatientId, resultNames, valueCol, datetimeCol, preTimeDelta, postTimeDelta):
        """
        Add on summary features to the patient-time instances.
        With respect to each index time, look for results within
        [indexTime+preTimeDelta, indexTime+postTimeDelta) and
        generate summary features like count, mean, median, std, first, last,
        proximate. Generic function, so have to specify the names of the value
        and datetime columns.

        Assume patientIdResultsByNameGenerator is actually a generator for each
        patient, so can only stream through results once.

        Store results in a temp file.
        """
        # Use results generator as outer loop as will not be able to random
        # access the contents.
        for patientId, resultsByName in resultsByNameByPatientId.iteritems():
            # Skip results if not in our list of patients of interest
            if patientId in patientEpisodeByIndexTimeById:
                patientEpisodeByIndexTime = patientEpisodeByIndexTimeById[patientId]
                resultsByName = resultsByNameByPatientId[patientId]
                self._addResultFeatures_singlePatient(patientEpisodeByIndexTime, \
                    resultsByName, resultNames, valueCol, datetimeCol, preTimeDelta, \
                    postTimeDelta)

        # Separate loop to verify all patient records addressed, even if no
        # results available (like an outer join).
        resultsByName = None
        for patientId, patientEpisodeByIndexTime in patientEpisodeByIndexTimeById.iteritems():
            self._addResultFeatures_singlePatient(patientEpisodeByIndexTime, \
                resultsByName, resultNames, valueCol, datetimeCol, preTimeDelta, \
                postTimeDelta)

    def _addResultFeatures_singlePatient(self, patientEpisodeByIndexTime, resultsByName, baseNames, valueCol, datetimeCol, preTimeDelta, postTimeDelta):
        """
        Add summary features to the patient-time instances.
        With respect to each index time, look for results within
        [indexTime+preTimeDelta, indexTime+postTimeDelta) and generate summary
        features like count, mean, median, std, first, last, proximate.
        Generic function, so have to specify the names of the value and datetime columns to look for.

        If resultsByName is None, then no results to match.
        Just make sure default / zero value columns are populated if
        they are not already.
        """
        preTimeDays = None
        if preTimeDelta is not None:
            preTimeDays = preTimeDelta.days
        postTimeDays = None
        if postTimeDelta is not None:
            postTimeDays = postTimeDelta.days

        # Init summary values to null for all results
        for indexTime, patient in patientEpisodeByIndexTime.iteritems():
            for baseName in baseNames:
                if resultsByName is not None or ("%s.%s_%s.count" % (baseName, preTimeDays, postTimeDays)) not in patient:
                    # Default to null for all values
                    patient["%s.%s_%s.count" % (baseName,preTimeDays,postTimeDays)] = 0
                    patient["%s.%s_%s.countInRange" % (baseName,preTimeDays,postTimeDays)] = 0
                    patient["%s.%s_%s.min" % (baseName,preTimeDays,postTimeDays)] = None
                    patient["%s.%s_%s.max" % (baseName,preTimeDays,postTimeDays)] = None
                    patient["%s.%s_%s.median" % (baseName,preTimeDays,postTimeDays)] = None
                    patient["%s.%s_%s.mean" % (baseName,preTimeDays,postTimeDays)] = None
                    patient["%s.%s_%s.std" % (baseName,preTimeDays,postTimeDays)] = None
                    patient["%s.%s_%s.first" % (baseName,preTimeDays,postTimeDays)] = None
                    patient["%s.%s_%s.last" % (baseName,preTimeDays,postTimeDays)] = None
                    patient["%s.%s_%s.diff" % (baseName,preTimeDays,postTimeDays)] = None
                    patient["%s.%s_%s.slope" % (baseName,preTimeDays,postTimeDays)] = None
                    patient["%s.%s_%s.proximate" % (baseName,preTimeDays,postTimeDays)] = None
                    patient["%s.%s_%s.firstTimeDays" % (baseName,preTimeDays,postTimeDays)] = None
                    patient["%s.%s_%s.lastTimeDays" % (baseName,preTimeDays,postTimeDays)] = None
                    patient["%s.%s_%s.proximateTimeDays" % (baseName,preTimeDays,postTimeDays)] = None

        # Have results available for this patient?
        if resultsByName is not None:
            for indexTime, patient in patientEpisodeByIndexTime.iteritems():
                # Time range limits on labs to consider
                preTimeLimit = None;
                postTimeLimit = None;

                # Time range limits on labs to consider
                if preTimeDelta is not None:
                    preTimeLimit = indexTime + preTimeDelta
                if postTimeDelta is not None:
                    postTimeLimit = indexTime + postTimeDelta

                for baseName in baseNames:
                    proximateValue = None
                    # Not all patients will have all labs checked
                    if resultsByName is not None and baseName in resultsByName:
                        firstItem = None
                        lastItem = None
                        # Item closest to the index time in time
                        proximateItem = None
                        filteredResults = list()
                        for result in resultsByName[baseName]:
                            resultTime = result[datetimeCol]
                            if resultTime is not None:
                                if (preTimeLimit is None or preTimeLimit <= resultTime) \
                                   and (postTimeLimit is None or resultTime < postTimeLimit):
                                    # Occurs within timeframe of interest, so record valueCol
                                    filteredResults.append(result)

                                    if firstItem is None or resultTime < firstItem[datetimeCol]:
                                        firstItem = result
                                    if lastItem is None or lastItem[datetimeCol] < resultTime:
                                        lastItem = result
                                    if proximateItem is None or (abs(resultTime - indexTime) < abs(proximateItem[datetimeCol] - indexTime)):
                                        proximateItem = result

                        if len(filteredResults) > 0:
                            # Count up number of values specifically labeled "in range"
                            valueList = columnFromModelList(filteredResults, valueCol)
                            patient["%s.%s_%s.count" % (baseName,preTimeDays,postTimeDays)] = len(valueList);
                            patient["%s.%s_%s.countInRange" % (baseName,preTimeDays,postTimeDays)] = self._countResultsInRange(filteredResults);
                            patient["%s.%s_%s.min" % (baseName,preTimeDays,postTimeDays)] = np.min(valueList);
                            patient["%s.%s_%s.max" % (baseName,preTimeDays,postTimeDays)] = np.max(valueList);
                            patient["%s.%s_%s.median" % (baseName,preTimeDays,postTimeDays)] = np.median(valueList);
                            patient["%s.%s_%s.mean" % (baseName,preTimeDays,postTimeDays)] = np.mean(valueList);
                            patient["%s.%s_%s.std" % (baseName,preTimeDays,postTimeDays)] = np.std(valueList);
                            patient["%s.%s_%s.first" % (baseName,preTimeDays,postTimeDays)] = firstItem[valueCol];
                            patient["%s.%s_%s.last" % (baseName,preTimeDays,postTimeDays)] = lastItem[valueCol];
                            patient["%s.%s_%s.diff" % (baseName,preTimeDays,postTimeDays)] = lastItem[valueCol] - firstItem[valueCol];
                            patient["%s.%s_%s.slope" % (baseName,preTimeDays,postTimeDays)] = 0.0;
                            timeDiffDays = ((lastItem[datetimeCol]-firstItem[datetimeCol]).total_seconds() / SECONDS_PER_DAY);
                            if timeDiffDays > 0.0:
                                patient["%s.%s_%s.slope" % (baseName,preTimeDays,postTimeDays)] = (lastItem[valueCol]-firstItem[valueCol]) / timeDiffDays;
                            patient["%s.%s_%s.proximate" % (baseName,preTimeDays,postTimeDays)] = proximateItem[valueCol];
                            patient["%s.%s_%s.firstTimeDays" % (baseName,preTimeDays,postTimeDays)] = (firstItem[datetimeCol]-indexTime).total_seconds() / SECONDS_PER_DAY;
                            patient["%s.%s_%s.lastTimeDays" % (baseName,preTimeDays,postTimeDays)] = (lastItem[datetimeCol]-indexTime).total_seconds() / SECONDS_PER_DAY;
                            patient["%s.%s_%s.proximateTimeDays" % (baseName,preTimeDays,postTimeDays)] = (proximateItem[datetimeCol]-indexTime).total_seconds() / SECONDS_PER_DAY;

        return

    # TODO(sbala): Fix isLabPanel arg declaration to be None by default.
    def _queryLabResultsByName(self, labNames, isLabPanel = True):
        """
        Query for all lab results that match with the given result base names.
        """
        # Verify patient list and/or patient episode has been processed.
        if not self.patientsProcessed:
            raise ValueError("Must process patients before lab results.")

        # Query rapid when filter by lab result type, limited to X records.
        # Filtering by patient ID drags down substantially until preloaded
        # table by doing a count on the SQR table?
        columnNames = [
            "CAST(pat_id AS bigint) as pat_id", "base_name", "ord_num_value",
            "result_flag", "result_in_range_yn"
        ]
        if LocalEnv.DATASET_SOURCE_NAME == 'STRIDE':
            columnNames += ["sor.result_time"]
        else:
            columnNames += ["result_time"]

        # Identify which patients to query.
        patientIds = set()
        patientEpisodes = self.getPatientEpisodeIterator()
        for episode in patientEpisodes:
            patientIds.add(episode[self.patientEpisodeIdColumn])
        # Construct query to pull from stride_order_results, stride_order_proc

        if LocalEnv.DATASET_SOURCE_NAME == 'STRIDE':
            query = SQLQuery()
            for column in columnNames:
                query.addSelect(column)
            query.addFrom("stride_order_results AS sor, stride_order_proc AS sop")
            query.addWhere("sor.order_proc_id = sop.order_proc_id")
            if isLabPanel:
                query.addWhereIn("proc_code", labNames)
            else:
                query.addWhereIn("base_name", labNames)

            query.addWhereIn("pat_id", patientIds)
            query.addOrderBy("pat_id")
            query.addOrderBy("sor.result_time")

            log.debug(query)
            return modelListFromTable(DBUtil.execute(query, includeColumnNames=True))


        else:

            query_str = "SELECT "
            for column in columnNames:
                query_str += column + ","
            query_str = query_str[:-1] + " FROM labs "

            if isLabPanel:
                clinicalItemType = 'proc_code'
            else:
                clinicalItemType = 'base_name'

            query_str += "WHERE %s IN (" % (clinicalItemType)
            for labName in labNames:
                query_str += "'%s'," % labName
            query_str = query_str[:-1] + ") "

            query_str += "AND pat_id IN "
            pat_list_str = "("
            for pat_id in patientIds:
                pat_list_str += str(pat_id) + ","
            pat_list_str = pat_list_str[:-1] + ") "
            query_str += pat_list_str

            query_str += "ORDER BY pat_id"
            if LocalEnv.DATASET_SOURCE_NAME == 'STRIDE':
                query_str += ", sor.result_time"
            else: # Implemented for UMich and UCSF
                query_str += ", result_time"

            cur = DBUtil.connection().cursor()
            cur.execute(query_str)

            results = []
            colNames = DBUtil.columnNamesFromCursor(cur)
            results.append(colNames)

            dataTable = list(cur.fetchall())
            for i, row in enumerate(dataTable):
                dataTable[i] = list(row);
            results.extend(dataTable);

            return modelListFromTable(results)


    def _parseResultsData(self, resultRowIter, patientIdCol, nameCol, valueCol, datetimeCol):
        """
        Wrapper for generator version to translate results into dictionary by
        patient ID for more consistent structure to parseClinicalItemData.
        """
        resultsByNameByPatientId = dict()
        for (patientId, resultsByName) in self._parseResultsDataGenerator(resultRowIter, patientIdCol, nameCol, valueCol, datetimeCol):
            resultsByNameByPatientId[patientId] = resultsByName
        return resultsByNameByPatientId

    def _parseResultsDataGenerator(self, resultRowIter, patientIdCol, nameCol, valueCol, datetimeCol):
        """
        General version of results data parser, which does not necessarily come
        from a file stream. Could be any reader / iterator over rows of item
        data. For example, from a TabDictReader over the temp file or
        modelListFromTable from database query results.
        """
        lastPatientId = None
        resultsByName = None
        for result in resultRowIter:
            if result[valueCol] is not None and result[valueCol] != NULL_STRING:
                patientId = int(result[patientIdCol])
                baseName = result[nameCol]
                try:
                    resultValue = float(result[valueCol])
                except Exception as e:
                    print "In _parseResultsDataGenerator, " \
                          "weird values of ord_num_value cannot be converted.. " \
                          "Exception:", e
                    continue
                resultTime = DBUtil.parseDateValue(result[datetimeCol])

                # Skip apparent placeholder values
                if resultValue < SENTINEL_RESULT_VALUE:
                    result[patientIdCol] = patientId
                    result[valueCol] = resultValue
                    result[datetimeCol] = resultTime

                    if patientId != lastPatientId:
                        # Encountering a new patient ID. Yield the results from
                        # the prior one before preparing for next one.
                        if lastPatientId is not None:
                            yield (lastPatientId, resultsByName)
                        lastPatientId = patientId
                        resultsByName = dict()
                    if baseName not in resultsByName:
                        resultsByName[baseName] = list()
                    resultsByName[baseName].append(result)

        # Yield last result
        if lastPatientId is not None:
            yield (lastPatientId, resultsByName)

    def _countResultsInRange(self,resultList):
        """
        Return the number of result models in the given list that represent
        "normal" "in range" values.
        """
        countInRange = 0
        for result in resultList:
            if "result_in_range_yn" in result and result["result_in_range_yn"] == "Y":
                countInRange += 1
        return countInRange

    def _getItemTimesByPatientId(self, clinicalItemEvents):
        """
        input: [{"patient_id":123, "item_date": 456}, ...]
        output: {123 : [456, 789]}
        """
        itemTimesByPatientId = dict()

        for itemData in clinicalItemEvents:
            # Convert patient_id to int and item_date to DBUtil.parseDateValue.
            # TODO(sbala): Stop relying on magic 0- and 1-indexes.
            patientId = int(itemData[0])
            itemTime = DBUtil.parseDateValue(itemData[1])
            itemData[0] = patientId
            itemData[1] = itemTime

            # Add item_date to itemTimesByPatientId
            if patientId not in itemTimesByPatientId:
                itemTimesByPatientId[patientId] = list()
            itemTimesByPatientId[patientId].append(itemTime)

        return itemTimesByPatientId

    def _readPatientEpisodesFile(self):
        """
        Read patient episodes into memory.
        """
        # Verify patient episodes have been processed.
        if not self.patientsProcessed:
            raise ValueError("Must process patient episodes before reading.")

        # Return iterator through _patientEpisodeTempFileName.
        iterator = TabDictReader(open(self._patientEpisodeTempFileName, "r"))
        patientEpisodes = [episode for episode in iterator]

        return patientEpisodes

    def processClinicalItemInput(self, clinicalItemName):
        """
        Process clinicalItemName for DB cursor.
        """
        patientEpisodes = self._readPatientEpisodesFile()
        pass

    def addTimeCycleFeatures(self, timeCol, timeAttr):
        """
        Look for a datetime value in the patientEpisode identified by timeCol.
        Add features to the patientEpisode based on the timeAttr string
        ("month","day","hour","minute","second"), including the sine and cosine
        of the timeAttr value relative to the maximum possible value to reflect
        cyclical time patterns (e.g. seasonal patterns over months in a year,
        or daily cycle patterns over hours in a day).
        """
        # Verify patient list and/or patient episode has been processed.
        if not self.patientsProcessed:
            raise ValueError("Must process patients before lab result.")

        # Open temp file.
        self._patientTimeCycleTempFileNameFormat
        tempFileName = self._patientTimeCycleTempFileNameFormat % (timeCol, timeAttr)
        tempFile = open(tempFileName, "w")

        # Write header fields to tempFile.
        tempFile.write("patient_id\tepisode_time\t")
        tempFile.write("%s.%s\t" % (timeCol, timeAttr))
        tempFile.write("%s.%s.sin\t" % (timeCol, timeAttr))
        tempFile.write("%s.%s.cos\n" % (timeCol, timeAttr))

        # Compute and write time cycle features.
        patientEpisodes = self.getPatientEpisodeIterator()
        for episode in patientEpisodes:
            timeObj = DBUtil.parseDateValue(episode[timeCol])
            # Use introspection (getattr) to extract some time feature from the
            # time object, as well as the maximum and minimum possible values
            # to set the cycle range.
            maxValue = getattr(timeObj.max, timeAttr)
            thisValue = getattr(timeObj, timeAttr)
            minValue = getattr(timeObj.min, timeAttr)

            radians = 2*np.pi * (thisValue-minValue) / (maxValue+1-minValue)

            # Write values to tempFile.
            tempFile.write("%s\t" % episode[self.patientEpisodeIdColumn])
            tempFile.write("%s\t" % episode[self.patientEpisodeTimeColumn])
            tempFile.write("%s\t" % thisValue)
            tempFile.write("%s\t" % np.sin(radians))
            tempFile.write("%s\n" % np.cos(radians))

        # Close tempFile.
        self._featureTempFileNames.append(tempFileName)
        tempFile.close()

    def loadMapData(self,filename):
        """
        Read the named file's contents through TabDictReader to enable data
        extraction. If cannot find file by absolute filename, then look under
        default mapdata directory.
        """
        try:
            return TabDictReader(open(filename))
        except IOError:
            # Unable to open file directly. See if it's in the mapdata directory
            appDir = os.path.dirname(Util.__file__)
            defaultFilename = os.path.join(appDir, "mapdata", filename)
            try:
                return TabDictReader(open(defaultFilename))
            except IOError:
                # May need to add default extension as well
                defaultFilename = defaultFilename + ".tab"
                return TabDictReader(open(defaultFilename))

    def addCharlsonComorbidityFeatures(self, features=None):
        """
        For each of a predefined set of comorbidity categories, add features
        summarizing occurrence of the associated ICD9 problems.
        """
        # Extract ICD9 prefixes per disease category
        icdprefixesByDisease = dict()
        if LocalEnv.DATASET_SOURCE_NAME == 'STRIDE':
            for row in self.loadMapData("CharlsonComorbidity-ICD9CM"):
                (disease, icd9prefix) = (row["charlson"], row["icd9cm"])
                if disease not in icdprefixesByDisease:
                    icdprefixesByDisease[disease] = list()
                    icdprefixesByDisease[disease].append("^ICD9." + icd9prefix)
        elif LocalEnv.DATASET_SOURCE_NAME == 'UMich':
            for row in self.loadMapData("CharlsonComorbidity-ICD9CM"):
                (disease, icd9prefix) = (row["charlson"], row["icd9cm"])
                if disease not in icdprefixesByDisease:
                    icdprefixesByDisease[disease] = list()
                    icdprefixesByDisease[disease].append(icd9prefix)
        elif LocalEnv.DATASET_SOURCE_NAME == 'UCSF':
            for row in self.loadMapData("CharlsonComorbidity-ICD10"):
                (disease, icd10prefix) = (row["Category"], row["Code"])
                if disease not in icdprefixesByDisease:
                    icdprefixesByDisease[disease] = list()
                    icdprefixesByDisease[disease].append("^ICD10." + icd10prefix)
                    icdprefixesByDisease[disease].append(icd10prefix)


        for disease, icdprefixes in icdprefixesByDisease.iteritems():
            disease = disease.translate(None," ()-/") # Strip off punctuation
            log.debug('Adding %s comorbidity features...' % disease)
            if LocalEnv.DATASET_SOURCE_NAME == 'STRIDE':
                self.addClinicalItemFeatures(icdprefixes, operator="~*", \
                                             label="Comorbidity." + disease, features=features)
            else:
                self.addClinicalItemFeatures_NonStanford(icdprefixes,
                                                         tableName = 'diagnoses',
                                                         clinicalItemType='diagnose_code',
                                                         clinicalItemTime='diagnose_time',
                                                         label="Comorbidity."+disease,
                                                         features=features)
        # TODO: Figure out the best way to handle UMich
        # icd9prefixesByDisease = dict()
        # for row in self.loadMapData("CharlsonComorbidity-ICD9CM"):
        #     (disease, icd9prefix) = (row["charlson"], row["icd9cm"])
        #     if disease not in icd9prefixesByDisease:
        #         icd9prefixesByDisease[disease] = list()
        #     if LocalEnv.DATASET_SOURCE_NAME == 'STRIDE':
        #         icd9prefixesByDisease[disease].append("^ICD9." + icd9prefix)
        #     elif LocalEnv.DATASET_SOURCE_NAME == 'UMich':
        #         icd9prefixesByDisease[disease].append(icd9prefix)
        #
        # '''
        # Solution:
        # For ICD9, map the whole code
        # For ICD10, only map the prefix
        # '''
        # if LocalEnv.DATASET_SOURCE_NAME == 'UMich':
        #     for row in self.loadMapData("CharlsonComorbidity-ICD10"):
        #         (disease, icd10prefix) = (row["charlson"], row["icd10"])
        #         if disease not in icd9prefixesByDisease:
        #             icd9prefixesByDisease[disease] = list()
        #         # icd9prefixesByDisease[disease].append(icd10prefix)
        #
        # for disease, icd9prefixes in icd9prefixesByDisease.iteritems():
        #     disease = disease.translate(None, " ()-/")  # Strip off punctuation
        #     log.debug('Adding %s comorbidity features...' % disease)
        #     if LocalEnv.DATASET_SOURCE_NAME == 'STRIDE':
        #         self.addClinicalItemFeatures(icd9prefixes, operator="~*", \
        #                                      label="Comorbidity." + disease, features=features)
        #     elif LocalEnv.DATASET_SOURCE_NAME == 'UMich':
        #         self.addClinicalItemFeatures_UMich(icd9prefixes,
        #                                            tableName='diagnoses',
        #                                            clinicalItemType='diagnose_code',
        #                                            clinicalItemTime='diagnose_time',
        #                                            label="Comorbidity." + disease,
        #                                            features=features)

    def addTreatmentTeamFeatures(self, features=None):
        """
        For each of a predefined set of specialty categories, add features
        summarizing the makeup of the treatment team.
        """
        # Extract out lists of treatment team names per care category
        teamNameByCategory = dict()

        if LocalEnv.DATASET_SOURCE_NAME == 'STRIDE':
            for row in self.loadMapData("TreatmentTeamGroups"):
                (category, teamName) = (row["team_category"], row["treatment_team"])
                if category not in teamNameByCategory:
                    teamNameByCategory[category] = list()
                teamNameByCategory[category].append(teamName)

            for category, teamNames in teamNameByCategory.iteritems():
                log.debug('Adding %s treatment team features...' % category)
                self.addClinicalItemFeatures(teamNames, column="description", \
                                                 label="Team." + category, features=features)

        elif LocalEnv.DATASET_SOURCE_NAME == 'UCSF':
            for row in self.loadMapData("TreatmentTeamGroups_UCSF"):
                (category, teamName) = (row["team_category"], row["treatment_team"])
                if category not in teamNameByCategory:
                    teamNameByCategory[category] = list()
                teamNameByCategory[category].append(teamName)

            for category, teamNames in teamNameByCategory.iteritems():
                log.debug('Adding %s treatment team features...' % category)
                # TODO sx: rename
                self.addClinicalItemFeatures_NonStanford(teamNames, \
                    tableName='labs', clinicalItemTime = 'order_time',
                    label="Team."+category, features=features)

    def addSexFeatures(self):
        SEX_FEATURES = ["Male", "Female"]
        for feature in SEX_FEATURES:
            self.addClinicalItemFeatures([feature], dayBins=[], \
                features="pre")

    def addRaceFeatures(self):
        for feature in self.queryAllRaces():
            self.addClinicalItemFeatures([feature], dayBins=[], \
                features="pre")

    def buildFeatureMatrix(self, header=None, matrixFileName=None):
        """
        Given a set of factory inputs, build a feature matrix which
        can then be output.

        For each input, use the following idiom to process:
        self._processFooInput()
            self._queryFooInput()
            self._parseFooInput()
        """
        # Initialize feature matrix file.
        if matrixFileName is None:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H.%M.%S")
            matrixFileName = "feature-matrix_%s.tab" % timestamp
            self._matrixFileName = matrixFileName
        if header is None:
            # file_name.tab
            # Created: timestamp
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            header = [
                '%s' % self._matrixFileName,
                'Created: %s' % timestamp
            ]
        self._matrixFileName = matrixFileName
        matrixFile = open(self._matrixFileName, "w")


        # Read arbitrary number of input temp files.
        # Use csv tab reader so we can just read the lists while being agnostic
        # to the actual fields in each of the various files.
        tempFiles = list()
        tempFileReaders = list()
        patientEpisodeFile = open(self._patientEpisodeTempFileName, "r")
        patientEpisodeReader = csv.reader(patientEpisodeFile, delimiter="\t")

        for tempFileName in self._featureTempFileNames:
            tempFile = open(tempFileName, "r")
            tempFileReader = csv.reader(tempFile, delimiter="\t")
            tempFiles.append(tempFile)
            tempFileReaders.append(tempFileReader)

        # Write header to matrix file.
        for line in header:
            matrixFile.write('# %s\n' % line)

        # Write data to matrix file.
        for patientEpisode in patientEpisodeReader:
            matrixData = list()
            # Add data from patientEpisodes.
            matrixData.extend(patientEpisode)
            # Each tempFile has the patientId and episodeTime fields.
            # Don't write these to the matrix file.
            for tempFileReader in tempFileReaders:
                tempData = tempFileReader.next()
                matrixData.extend(tempData[2:])

            # Write data to matrixFile, with trailing \n.
            matrixFile.write("\t".join(matrixData))
            matrixFile.write("\n")

        self.cleanTempFiles()

    def cleanTempFiles(self):
        # Close temp files.
        try:
            [tempFile.close() for tempFile in tempFiles]
        except:
            pass
        # Clean up temp files.
        for tempFileName in self._featureTempFileNames:
            try:
                os.remove(tempFileName)
            except OSError:
                pass
        # Clean up patient_episode file.
        try:
            os.remove(self._patientEpisodeTempFileName)
        except OSError:
            pass
        # Clean up patient_list file.
        try:
            os.remove(self._patientListTempFileName)
        except OSError:
            pass

    def _getMatrixIterator(self):
        return TabDictReader(open(self._matrixFileName, "r"))

    def readFeatureMatrixFile(self):
        reader = csv.reader(open(self._matrixFileName, "r"), delimiter="\t")
        # reader = self._getMatrixIterator()
        featureMatrixData = [episode for episode in reader]

        return featureMatrixData

    def getMatrixFileName(self):
        return self._matrixFileName

    def getNumRows(self):
        return self._numRows

    def queryAllRaces(self):
        '''
        In case that not all data are accessible for us beforehand,
        we need to do a first "peek" of all possible Races.

        Returns:

        '''
        if LocalEnv.DATASET_SOURCE_NAME == 'STRIDE':
            RACE_FEATURES = [
                "RaceWhiteHispanicLatino", "RaceWhiteNonHispanicLatino",
                "RaceHispanicLatino", "RaceBlack", "RaceAsian",
                "RacePacificIslander", "RaceNativeAmerican",
                "RaceOther", "RaceUnknown"
            ]
            return RACE_FEATURES
        else:
            RACE_FEATURES = ['Caucasian', 'Unknown', 'African American',
                             'American Indian or Alaska Native', 'Patient Refused',
                             'Native Hawaiian and Other Pacific Islander',
                             'Other', 'Middle Eastern', 'Hispanic', 'Multi Racial',
                             'Asian - Pacific Islander', 'Asian']

            # query = SQLQuery()
            # query.addSelect("DISTINCT RaceName")
            # query.addFrom("demographics")
            # results = DBUtil.execute(query)
            # results = [x[0] for x in results]
            # results = [x if x else 'Unknown' for x in results]
            return RACE_FEATURES

    # def queryAllTeams(self):
    #     if LocalEnv.DATASET_SOURCE_NAME == 'UCSF':
    #         query = SQLQuery()
    #         query.addSelect("DISTINCT RaceName")
    #         query.addFrom("demographics")
    #         results = DBUtil.execute(query)
    #         results = [x[0] for x in results]
    #         # results = [x if x else 'Unknown' for x in results]
    #         return results
