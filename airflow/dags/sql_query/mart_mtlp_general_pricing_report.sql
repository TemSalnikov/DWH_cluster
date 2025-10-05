drop table kafka.mdlp_general_pricing_report on cluster cluster_2S_2R

create table kafka.mdlp_general_pricing_report on cluster cluster_2S_2R
(
	
	tin_to_the_issuer text, 
	the_name_of_the_issuer text, 
	code_of_the_subject_of_the_russian_federation text, 
	the_subject_of_the_russian_federation text,
	tin_of_the_participant text, 
	name_of_the_participant text, 
	mnn text, 
	trade_name text, 
	gtin text, 
	the_number_of_points_of_sales text, 
	sales_volume_units text, 
	meduvented_price_rub text, 
	source_of_financing text, 
	data_update_date text, 
	type_report text, 
	date_to text, 
	create_dttm text, 
	deleted_flag bool, 
	uuid_report text
)
engine = Kafka()
SETTINGS
    kafka_broker_list = 'kafka1:19092, kafka2:19092, kafka3:19092',
    kafka_topic_list = 'mdlp_general_pricing_report',
    kafka_group_name = 'clickhouse',
    kafka_format = 'JSONColumns',
    kafka_num_consumers = 1;



drop VIEW kafka.mdlp_general_pricing_report_mv on cluster cluster_2S_2R 
	
CREATE MATERIALIZED VIEW kafka.mdlp_general_pricing_report_mv on cluster cluster_2S_2R 
TO stg.mart_mdlp_general_pricing_report AS
SELECT * FROM kafka.mdlp_general_pricing_report;


drop table stg.mart_mdlp_general_pricing_report on cluster cluster_2S_2R

create table stg.mart_mdlp_general_pricing_report on cluster cluster_2S_2R
(

	tin_to_the_issuer text, 
	the_name_of_the_issuer text, 
	code_of_the_subject_of_the_russian_federation text, 
	the_subject_of_the_russian_federation text,
	tin_of_the_participant text, 
	name_of_the_participant text, 
	mnn text, 
	trade_name text, 
	gtin text, 
	the_number_of_points_of_sales text, 
	sales_volume_units text, 
	meduvented_price_rub text, 
	source_of_financing text, 
	data_update_date text, 
	type_report text, 
	date_to text, 
	create_dttm text, 
	deleted_flag bool, 
	uuid_report text
)
engine = ReplacingMergeTree()
order by (uuid_report, gtin, tin_to_the_issuer, tin_of_the_participant, deleted_flag)

select * from cluster('cluster_2S_2R', 'stg', 'mart_mdlp_general_pricing_report')
