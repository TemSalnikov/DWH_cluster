drop table kafka.mdlp_general_report_on_disposalon on cluster cluster_2S_2R

create table kafka.mdlp_general_report_on_disposal on cluster cluster_2S_2R
(
	date_of_disposal text, 
	tin_to_the_issuer text, 
	the_name_of_the_issuer text, 
	code_of_the_subject_of_the_russian_federation text, 
	the_subject_of_the_russian_federation text, 
	settlement text, 
	district text, 
	tin_of_the_participant text, 
	name_of_the_participant text, 
	identifier_md_participant text, 
	address text, 
	mnn text, 
	trade_name text, 
	gtin text, 
	series text, 
	best_before_date text, 
	type_of_disposal text, 
	the_volume_of_diving_units text, 
	source_of_financing text, 
	data_update_date text, 
	type_of_export text, 
	completeness_of_disposal text, 
	type_report text, 
	date_to text, 
	create_dttm text, 
	deleted_flag bool, 
	uuid_report text
	)
engine = Kafka()
SETTINGS
    kafka_broker_list = 'kafka1:19092, kafka2:19092, kafka3:19092',
    kafka_topic_list = 'mdlp_general_report_on_disposal',
    kafka_group_name = 'clickhouse',
    kafka_format = 'JSONColumns',
    kafka_num_consumers = 1;


drop VIEW kafka.mdlp_general_report_on_disposalon_mv on cluster cluster_2S_2R 
	
CREATE MATERIALIZED VIEW kafka.mdlp_general_report_on_disposal_mv on cluster cluster_2S_2R 
TO stg.mart_mdlp_general_report_on_disposal AS
SELECT * FROM kafka.mdlp_general_report_on_disposal;


drop table stg.mart_mdlp_general_report_on_disposalon on cluster cluster_2S_2R

create table stg.mart_mdlp_general_report_on_disposal on cluster cluster_2S_2R
(
	date_of_disposal text, 
	tin_to_the_issuer text, 
	the_name_of_the_issuer text, 
	code_of_the_subject_of_the_russian_federation text, 
	the_subject_of_the_russian_federation text, 
	settlement text, 
	district text, 
	tin_of_the_participant text, 
	name_of_the_participant text, 
	identifier_md_participant text, 
	address text, 
	mnn text, 
	trade_name text, 
	gtin text, 
	series text, 
	best_before_date text, 
	type_of_disposal text, 
	the_volume_of_diving_units text, 
	source_of_financing text, 
	data_update_date text, 
	type_of_export text, 
	completeness_of_disposal text, 
	type_report text, 
	date_to text, 
	create_dttm text, 
	deleted_flag bool, 
	uuid_report text
)
engine = ReplacingMergeTree()
order by (uuid_report, gtin, tin_to_the_issuer, deleted_flag)

select * from cluster('cluster_2S_2R', 'stg', 'mart_mdlp_general_report_on_disposalon')
