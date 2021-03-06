sync_environment = "/Users/jonc101/Box Sync/Jonathan Chiang's Files/mining-clinical-decisions/"
#sync_environment = "/Users/jonc101/Box Sync/Jonathan Chiang's Files/audit_log/"
#install.packages("data.table")

# libraries to read in
library(bigrquery)
library(data.table)
library(feather)
library(reticulate)
library(dplyr)
library(psych)
library(timevis)
library(shiny)

# python libraries 
pandas <- import("pandas")
pa <- import("pyarrow")
pq <- pa$parquet

# Google Project Name 
project <- "mining-clinical-decisions" # put your project ID here

# writes csv to Sync Folder
push_quiver <- function(df, name, env){
  write.csv(df, paste0(env ,name,".csv"))
}

# writes df to feather format to Sync Folder
push_quiver_feather <- function(df, name, env){
  write_feather(df, paste0(env ,name,".feather"))
}

# lists files from Sync Folder
list_quiver_csv <- function(env){
  files <- list.files(env, pattern='*\\.csv', recursive=TRUE)
  return(unlist(as.vector(strsplit(files, ".csv"))))
}

# Lists feather files from Sync Folder
list_quiver_feather <- function(env){
  files <- list.files(env, pattern='*\\.feather', recursive=TRUE)
  return(unlist(as.vector(strsplit(files, ".feather"))))
}

# reads CSV from Sync Folder
read_quiver <- function(file,env){
  return(read.csv(paste0(env,file,".csv")))
}

# reads CSV using fread 
fread_quiver <- function(file,env){
  return(fread(paste0(env,file,".csv")))
}

# reads feather from sync folder
fread_quiver_feather <- function(file,env){
  return(read_feather(paste0(env,file,".feather")))
}


# generic reticulate function to read Parquet file in R
read_parquet <- function(path, columns = NULL) {
  
  path <- path.expand(path)
  path <- normalizePath(path)
  
  if (!is.null(columns)) columns = as.list(columns)
  
  xdf <- pandas$read_parquet(path, columns = columns)
  
  xdf <- as.data.frame(xdf, stringsAsFactors = FALSE)
  
  dplyr::tbl_df(xdf)
  
}


# File Read System 
stroke_cohort       <- fread_quiver("stroke_cohort", sync_environment)
stroke_cohort_demo  <- fread_quiver("stroke_cohort_demo", sync_environment)

# splits patients into individual lists 
patient_list <- split(stroke_cohort,stroke_cohort$jc_uid)

# patient 1: need to convert to timevis format 
p1 <- patient_list$JCcb69cc

# DESIRED DATA FORMAT RESULT 
timevisData <- data.frame(
  id = 1:11,
  content = c("Open", "Open",
              "Open", "Open", "Half price entry",
              "Staff meeting", "Open", "Adults only", "Open", "Hot tub closes",
              "Siesta"),
  start = c("2016-05-01 07:30:00", "2016-05-01 14:00:00",
            "2016-05-01 06:00:00", "2016-05-01 14:00:00", "2016-05-01 08:00:00",
            "2016-05-01 08:00:00", "2016-05-01 08:30:00", "2016-05-01 14:00:00",
            "2016-05-01 16:00:00", "2016-05-01 19:30:00",
            "2016-05-01 12:00:00"),
  end   = c("2016-05-01 12:00:00", "2016-05-01 20:00:00",
            "2016-05-01 12:00:00", "2016-05-01 22:00:00", "2016-05-01 10:00:00",
            "2016-05-01 08:30:00", "2016-05-01 12:00:00", "2016-05-01 16:00:00",
            "2016-05-01 20:00:00", NA,
            "2016-05-01 14:00:00"),
  group = c(rep("lib", 2), rep("gym", 3), rep("pool", 5), NA),
  type = c(rep("range", 9), "point", "background")
)

timevisDataGroups <- data.frame(
  id = c("lib", "gym", "pool"),
  content = c("Lab", "Emergency Room", "CT Head")
)

# write a function to convert single patient to timeline vis data frame format 

# time start is inpatient admit time 

# group1 = time to CT head order 
# group2 = time to TPA order 
# group3 = time from order to admin 
# group4 = time from emergency admit time to inpatient admit time 

start    <- p1 %>% select(emergencyAdmitTime) #admit_time
end  <-  p1 %>% select(ctHeadOrderTime) #ct_order_time
content <- "CT Head Order Time"
group <- "EHR"
type <- "RANGE"
id <- 1
t <- cbind(start,end,content,group,type,id)
colnames(t) <- c("start","end","content","group","type","id")


# function to clean data 
# 
library(lubridate)
#with_tz(ymd_hms(stroke_cohort$emergencyAdmitTime),"America/Los_Angeles")

convert_datetime <- function(timeEHR){
  #convert to America_Pacific in lubridate
  # requires format like this
  # "2014-06-18 17:21:00" "2014-08-05 16:14:00" "2014-08-31 19:10:00" "2014-09-02 19:23:00" "2014-09-24 15:27:00" "2014-09-27 16:21:00" "2014-09-27 18:16:00"
  # "2014-09-28 18:46:00" "2014-10-18 15:55:00" "2014-10-29 19:21:00" "2014-10-29 22:53:00" "2014-10-30 18:52:00" "2014-11-10 13:30:00" "2014-11-23 18:21:00"
  # "2014-11-25 11:43:00" "2014-11-29 10:17:00"
  
  #into this format
  
  #[31] "2011-10-17 06:19:00 PDT" "2011-11-06 07:03:00 PST" "2011-11-07 12:36:00 PST" "2011-11-12 03:29:00 PST" "2011-11-16 23:37:00 PST"
  #[36] "2011-11-18 09:11:00 PST" "2011-11-29 05:21:00 PST" "2011-12-11 09:54:00 PST" "2011-12-19 01:49:00 PST" "2011-12-21 04:14:00 PST"
  #[41] "2012-01-04 10:31:00 PST" "2012-01-22 09:31:00 PST" 
  return(with_tz(ymd_hms(timeEHR),"America/Los_Angeles"))
}


find_time_difference <- function(time_start,time_end, jc_uid){
    time_to_ct <- as.numeric(convert_datetime(time_end) - convert_datetime(time_start)) /60
    #return(time_to_ct)
    ct.df <- as_tibble(cbind(jc_uid, time_to_ct))
    colnames(ct.df)[1] <- "id"
    colnames(ct.df)[2] <- "time_diff"
    ct.df$time_diff <- as.numeric(ct.df$time_diff)
    return(ct.df)
}


plot_density_difference_plotly <- function(dataframe){
  #ct.df2 <- dataframe %>% filter(time_diff < 100)
  pg2  <- ggplot(dataframe, aes(x=time_diff)) + 
    geom_histogram(aes(y=..density..),      # Histogram with density instead of count on y-axis
                   binwidth=1,
                   colour="black", fill="white") +
    geom_density(alpha=.2, fill="#FF6666")   # Overlay with transparent density plot 
  return(plotly::ggplotly(pg2))
}

plot_density_difference <- function(dataframe){
  #ct.df2 <- dataframe %>% filter(time_diff < 100)
  pg2  <- ggplot(dataframe, aes(x=time_diff)) + 
    geom_histogram(aes(y=..density..),      # Histogram with density instead of count on y-axis
                   binwidth=1,
                   colour="black", fill="white") +
    geom_density(alpha=.2, fill="#FF6666")   # Overlay with transparent density plot 
  return(pg2)
}

plot_density_difference_long <- function(dataframe){
  #ct.df2 <- dataframe %>% filter(time_diff < 100)
  pg2  <- ggplot(dataframe, aes(x=time_diff,color = event)) + 
    geom_histogram(aes(y=..density..),      # Histogram with density instead of count on y-axis
                   binwidth=1) +
    geom_density(alpha=.2) + ggtitle("Stroke Density Plot Histograms") +
    xlab("Time Differences in Minutes") + ylab("Density")  # Overlay with transparent density plot 
  return(pg2)
}

plot_density_difference_long_facet <- function(dataframe){
  #ct.df2 <- dataframe %>% filter(time_diff < 100)
  pg2  <- ggplot(dataframe, aes(x=time_diff,color = event)) + 
    geom_histogram(aes(y=..density..),      # Histogram with density instead of count on y-axis
                   binwidth=1) +
    geom_density(alpha=.2) +  # Overlay with transparent density plot 
    facet_grid(rows = vars(event)) + ggtitle("Stroke Density Histograms") +
    xlab("Time Differences in Minutes") + ylab("Density") + 
    theme(
    plot.title = element_text(color="red", size=14, face="bold.italic",hjust = 0.5),
    axis.title.x = element_text(color="blue", size=14, face="bold"),
    axis.title.y = element_text(color="#993333", size=14, face="bold"))
  return(pg2)
}



test1 <- find_time_difference(stroke_cohort$emergencyAdmitTime, stroke_cohort$ctHeadOrderTime, stroke_cohort$jc_uid)
test1.1 <- test1 %>% filter(time_diff < 100) %>% filter(time_diff > -16 )

test2 <- find_time_difference(stroke_cohort$emergencyAdmitTime, stroke_cohort$inpatientAdmitTime, stroke_cohort$jc_uid)
test2.1 <- test2 %>% filter(time_diff < 100) %>% filter(time_diff > -16 )

test3 <- find_time_difference(stroke_cohort$emergencyAdmitTime, stroke_cohort$tpaOrderTime, stroke_cohort$jc_uid)
test3.1 <- test3 %>% filter(time_diff < 100) %>% filter(time_diff > -16 )

test4 <- find_time_difference(stroke_cohort$emergencyAdmitTime, stroke_cohort$tpaAdminTime, stroke_cohort$jc_uid)
test4.1 <- test4 %>% filter(time_diff < 100) %>% filter(time_diff > -16 )

test5 <- find_time_difference(stroke_cohort$tpaOrderTime, stroke_cohort$tpaAdminTime, stroke_cohort$jc_uid)
test5.1 <- test5 %>% filter(time_diff < 100) %>% filter(time_diff > -16 )

test1.1$event <- 'ER to CT Order' # Try: Red: Time diff between ERAdmitTime to CT Head Order
test2.1$event <- 'ER to Inpatient' # Time diff between ERAdmitTime to Inpatient Transfer
test3.1$event <- 'ER to tPA Order' # Green: Time diff between ERAdmitTime to tPA Order
test4.1$event <- 'ER to tPAAdmin' # Blue: Time diff between ERAdmitTime to tPA administration (unless there's a way to tie directly to previous?)

test5.1$event <- 'tPA Order to Admin'


test_time_long <- rbind(test1.1, 
                        test3.1,
                        test2.1,
                        test4.1)
                        #test5.1)



plot_density_difference(test1.1)
plot_density_difference(test2.1)
plot_density_difference(test3.1)
plot_density_difference(test4.1)
plot_density_difference(test5.1)



# 
colnames(stroke_cohort)
colnames(stroke_cohort_demo)
stroke_cohort_demo$jc_uid <- stroke_cohort_demo$rit_uid

stroke_cohort_merge <- merge(stroke_cohort, stroke_cohort_demo, by= "jc_uid")
sdf <- stroke_cohort_merge

# push_quiver <- function(df, name, env){
# push_quiver(stroke_cohort_merge, "stroke_cohort_merge", sync_environment)
# list_quiver_csv(sync_environment)


test6 <- find_time_difference(sdf$emergencyAdmitTime, sdf$ctHeadOrderTime, sdf$jc_uid)
# Try: Red: Time diff between ERAdmitTime to CT Head Order
# Green: Time diff between ERAdmitTime to tPA Order
# Blue: Time diff between ERAdmitTime to tPA administration (unless there's a way to tie directly to previous?)
# Time diff between ERAdmitTime to Inpatient Transfer

# changnig colors 
#http://www.cookbook-r.com/Graphs/Colors_(ggplot2)/

