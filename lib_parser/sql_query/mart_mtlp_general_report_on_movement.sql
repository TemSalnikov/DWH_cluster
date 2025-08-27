drop table kafka.mdlp_general_report_on_movement on cluster cluster_2S_2R

create table kafka.mdlp_general_report_on_movement on cluster cluster_2S_2R
(
	
	the_date_of_the_operation text, 
	tin_to_the_issuer text, 
	the_name_of_the_issuer text, 
	mnn text, 
	trade_name text, 
	gtin text, 
	series text, 
	operation_number text, 
	tin_of_the_sender text, 
	name_of_the_sender text, 
	identifier_md_of_the_sender text, 
	tin_of_the_recipient text, 
	name_of_the_recipient text, 
	identifier_md_of_the_recipient text, 
	quantity_units text, 
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
    kafka_topic_list = 'mdlp_general_report_on_movement',
    kafka_group_name = 'clickhouse',
    kafka_format = 'JSONColumns',
    kafka_num_consumers = 1;

alter table kafka.mdlp_general_report_on_movement on cluster cluster_2S_2R 
MODIFY column deleted_flag bool;
	
drop VIEW kafka.mdlp_general_report_on_movement_mv on cluster cluster_2S_2R 
	
CREATE MATERIALIZED VIEW kafka.mdlp_general_report_on_movement_mv on cluster cluster_2S_2R 
TO stg.mart_mdlp_general_report_on_movement AS
SELECT * FROM kafka.mdlp_general_report_on_movement;


drop table stg.mart_mdlp_general_report_on_movement on cluster cluster_2S_2R

create table stg.mart_mdlp_general_report_on_movement on cluster cluster_2S_2R
(
	the_date_of_the_operation text, 
	tin_to_the_issuer text, 
	the_name_of_the_issuer text, 
	mnn text, 
	trade_name text, 
	gtin text, 
	series text, 
	operation_number text, 
	tin_of_the_sender text, 
	name_of_the_sender text, 
	identifier_md_of_the_sender text, 
	tin_of_the_recipient text, 
	name_of_the_recipient text, 
	identifier_md_of_the_recipient text, 
	quantity_units text, 
	source_of_financing text, 
	data_update_date text, 
	type_report text, 
	date_to text, 
	create_dttm text, 
	deleted_flag bool, 
	uuid_report text
)
engine = ReplacingMergeTree()
order by (uuid_report, gtin, tin_to_the_issuer, deleted_flag)

alter table stg.mart_mdlp_general_report_on_movement on cluster cluster_2S_2R 
MODIFY column deleted_flag bool;

select uuid_report, count(*) from cluster('cluster_2S_2R', 'stg', 'mart_mdlp_general_report_on_movement')
group by uuid_report
