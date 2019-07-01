
# 斯坦福HealthRex实验室
## PI：Jonathan Chen（http://web.stanford.edu/~jonc101）

对于初学者，想要了解项目的数据源、源代码、实验室/组的基础结构，请查看Wiki（https://github.com/HealthRex/CDSS/wiki）。

代码免费提供给学术用途，对于使用有的任何疑问，请发送电子邮件至stanford [dot] healthrex [at] gmail [dot] com。

Suggested citation: Chen, J. H., Podchiyska, T. & Altman, R. B. Journal of the American Medical Informatics Association ocv091 (2016). doi:10.1093/jamia/ocv091

代码库指南： 
* 避免使用任何大型数据文件，因此repo保持轻量级，以便新开发人员快速下载/克隆。
* 对于一次性或非常项目的特定文件和脚本，基本上可以在/ scripts目录下的工作区中执行任何操作（但同样，请避免使用大数据文件并避免任何私人/患者信息，包括包含个人的分析结果患者项目，因为这个回购将公开访问）。
* 尝试将可重用组件推广到medinfo核心应用程序模块。 

目录的简介
* medinfo/analysis - General purpose analysis and data manipulation modules, not specific to any type of project. For example, serially calculating t-tests, list rank similarity measures, ROC plots, precision-recall curves, SQL-like manipulation functions for CSV / TSV files.  
  *非特定项目的通用的数据分析和处理模块，例如，连续计算t检验，列表排名相似性度量，ROC图，精确回忆曲线，CSV / TSV文件的类似SQL的操作函数。*
* medinfo/common - General purpose computing utilities, such as calculating different 2x2 contingency stats, adding progress trackers to long processes.  
  *通用计算实用程序，例如计算不同的2x2意外事件统计数据，向长进程添加进度跟踪器。*
* medinfo/cpoe - More project specific applications related to Computerized Physician Order Entry projects, implementing different approaches to clinical order recommendations and evaluating/analyzing them with different experiments on historical data. Application code for clinical case simulations for users to interact with.  
  *文件夹中都是与电子医嘱系统相关的应用，根据对历史数据的各种实验，实现不同的原型来对临床遗嘱进行建议和分析。还有供使用者对临床Case模拟的代码。*
* medinfo/dataconversion - General and project specific utilities to pre-process data sources. Given a dump of hospital data, conversion scripts to unify into a simplified / pre-processed clinical_item transaction series. FeatureMatrixFactory to extract out clinical data into simple "feature matrix" / dataframe form to feed into assorted learning algorithms. Subdirecties with additional supporting mapping data (e.g., ICD9 codes to Charlson comorbidity categories).  
  *用于预处理数据源的常规和项目特定实用程序。给定医院数据转储，转换脚本统一为简化/预处理的clinical_item交易系列。 FeatureMatrixFactory将临床数据提取为简单的“特征矩阵”/数据框形式，以提供各种学习算法。具有附加支持映射数据的子目录（例如，ICD9代码到Charlson合并症类别）。*
* medinfo/db - Utilities to connect between Python code and SQL databases, with a relatively plain JSON-like model of tables represented by lists of dictionaries (name-value pairs of each row of data). ResultsFormatter has several convenience functions to interconvert between SQL data tables, CSV/TSV plain text files, Pandas dataframes, and JSON-like lists of Python dictionaries. Several project specific application database schemas in the definition subdirectory. Support subdirectory with "dump" and "restore" convenience scripts to move database content between systems.  
  *用于连接Python代码和SQL数据库的实用程序，具有由字典列表（每行数据的名称 - 值对）表示的相对简单的类似JSON的表模型。 ResultsFormatter有几个便利函数来互换SQL数据表，CSV / TSV纯文本文件，Pandas数据帧和类似JSON的Python字典列表。定义子目录中的几个项目特定的应用程序数据库模式。支持带有“dump”和“restore”便捷脚本的子目录，以在系统之间移动数据库内容。*
* medinfo/geography - Not much here yet. One example of how to generate data labeled geographic maps of the US.
  *这里还不多。如何生成标记为美国的地理地图的数据的一个示例。*
* medinfo/textanalysis - Not much here yet. One example of a project specific parsing script that translates a stream of text documents into an interactive HTML file that attempts to auto-annotate features of the documents based on Python coded annotator classes. 
   *这里还不多。项目特定解析脚本的一个示例，它将文本文档流转换为交互式HTML文件，该文件尝试基于Python编码的注释器类自动注释文档的功能。*
* medinfo/web - View and Controller layer for web interface to application functions.
  *用于Web界面到应用程序功能的视图和控制器层*
 
**以下为源英文内容**
------------------------------------------------
# HealthRex Laboratory at Stanford University
## PI: Jonathan Chen (http://web.stanford.edu/~jonc101)

Review the Wiki (https://github.com/HealthRex/CDSS/wiki) for Starter Notes on using some of the common data sources and codebase as well as general lab/group infrastructure.

Code is made freely available for academic use. For questions about usage, email stanford [dot] healthrex [at] gmail [dot] com.

Suggested citation: Chen, J. H., Podchiyska, T. & Altman, R. B. Journal of the American Medical Informatics Association ocv091 (2016). doi:10.1093/jamia/ocv091

General Guidelines for Code Repo:
* Avoid any large data files, so the repo stays lightweight for new devs to quickly download/clone.
* For one-off or very project specific files and scripts, basically do whatever you want in the workspace areas under the /scripts directory (but again, avoid big data files and also avoid any private / patient information, including analysis results that include individual patient items, as this repo will publicly accessible).
* Try to promote reusable components to the medinfo core application modules.

Broad description of core application directories
* medinfo/analysis - General purpose analysis and data manipulation modules, not specific to any type of project. For example, serially calculating t-tests, list rank similarity measures, ROC plots, precision-recall curves, SQL-like manipulation functions for CSV / TSV files.
* medinfo/common - General purpose computing utilities, such as calculating different 2x2 contingency stats, adding progress trackers to long processes.
* medinfo/cpoe - More project specific applications related to Computerized Physician Order Entry projects, implementing different approaches to clinical order recommendations and evaluating/analyzing them with different experiments on historical data. Application code for clinical case simulations for users to interact with.
* medinfo/dataconversion - General and project specific utilities to pre-process data sources. Given a dump of hospital data, conversion scripts to unify into a simplified / pre-processed clinical_item transaction series. FeatureMatrixFactory to extract out clinical data into simple "feature matrix" / dataframe form to feed into assorted learning algorithms. Subdirecties with additional supporting mapping data (e.g., ICD9 codes to Charlson comorbidity categories).
* medinfo/db - Utilities to connect between Python code and SQL databases, with a relatively plain JSON-like model of tables represented by lists of dictionaries (name-value pairs of each row of data). ResultsFormatter has several convenience functions to interconvert between SQL data tables, CSV/TSV plain text files, Pandas dataframes, and JSON-like lists of Python dictionaries. Several project specific application database schemas in the definition subdirectory. Support subdirectory with "dump" and "restore" convenience scripts to move database content between systems.
* medinfo/geography - Not much here yet. One example of how to generate data labeled geographic maps of the US.
* medinfo/textanalysis - Not much here yet. One example of a project specific parsing script that translates a stream of text documents into an interactive HTML file that attempts to auto-annotate features of the documents based on Python coded annotator classes.
* medinfo/web - View and Controller layer for web interface to application functions.

	 
