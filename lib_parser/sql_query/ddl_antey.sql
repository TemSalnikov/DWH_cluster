
create table stg.mart_fpc_antey_drugstor on cluster cluster_2S_2R
(
	drugstore text,
	inn bigint,
	address text,
	hash_drugstore text
)
engine = ReplacingMergeTree()
order by (hash_drugstore)


--drop table kafka.fpc_antey_drugstor on cluster cluster_2S_2R

create table kafka.fpc_antey_drugstor on cluster cluster_2S_2R
(
	drugstore text,
	inn bigint,
	address text,
	hash_drugstore text
)
engine = Kafka()
SETTINGS
    kafka_broker_list = 'kafka1:19092, kafak2:19092, kafka3:19092',
    kafka_topic_list = 'fpc_antey_table_drugstor',
    kafka_group_name = 'clickhouse',
    kafka_format = 'JSONColumns',
    kafka_num_consumers = 1;



--drop VIEW kafka.fpc_antey_drugstor_mv on cluster cluster_2S_2R

CREATE MATERIALIZED VIEW kafka.fpc_antey_drugstor_mv on cluster cluster_2S_2R TO stg.mart_fpc_antey_drugstor AS
SELECT * FROM kafka.fpc_antey_drugstor;


--
--drop table stg.mart_fpc_antey_report on cluster cluster_2S_2R

create table stg.mart_fpc_antey_report on cluster cluster_2S_2R
(
	uuid_report text,
	product text,
	supplier text,
	quantity text,
	price text,
	total_cost text,
	name_report text,
	name_pharm_chain text,
	report_date text,
	start_date text,
	end_date text,
	processed_dttm text
)
engine = ReplacingMergeTree()
order by (uuid_report)


--drop table kafka.fpc_antey_report on cluster cluster_2S_2R

create table kafka.fpc_antey_report on cluster cluster_2S_2R
(
	uuid_report text,
	product text,
	supplier text,
	quantity text,
	price text,
	total_cost text,
	name_report text,
	name_pharm_chain text,
	report_date text,
	start_date text,
	end_date text,
	processed_dttm text
)
engine = Kafka()
SETTINGS
    kafka_broker_list = 'kafka1:19092, kafak2:19092, kafka3:19092',
    kafka_topic_list = 'fpc_antey_table_report',
    kafka_group_name = 'clickhouse',
    kafka_format = 'JSONColumns',
    kafka_max_block_size = 10485760,
    kafka_poll_max_batch_size = 10485760,
    kafka_handle_error_mode = 'stream',
    kafka_num_consumers = 1;


--drop VIEW kafka.fpc_antey_report_mv on cluster cluster_2S_2R

CREATE MATERIALIZED VIEW kafka.fpc_antey_report_mv  on cluster cluster_2S_2R TO stg.mart_fpc_antey_report AS 
SELECT * FROM kafka.fpc_antey_report;

