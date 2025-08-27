drop table kafka.mdlp_general_report_on_remaining_items on cluster cluster_2S_2R

create table kafka.mdlp_general_report_on_remaining_items on cluster cluster_2S_2R
(
	uuid_report text,
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
	remains_in_the_market_units text, 
	remains_before_the_input_in_th_units text, 
	general_residues_units text, 
	source_of_financing text, 
	data_update_date text, 
	remains_in_the_market_excluding_705_unitary_enterprise text, 
	shipped text, 
	type_report text, 
	date_to text, 
	create_dttm text, 
	deleted_flag bool
)
engine = Kafka()
SETTINGS
    kafka_broker_list = 'kafka1:19092, kafka2:19092, kafka3:19092',
    kafka_topic_list = 'mdlp_general_report_on_remaining_items',
    kafka_group_name = 'clickhouse',
    kafka_format = 'JSONColumns',
    kafka_num_consumers = 1;

drop VIEW kafka.mdlp_general_report_on_remaining_items_mv on cluster cluster_2S_2R 

CREATE MATERIALIZED VIEW kafka.mdlp_general_report_on_remaining_items_mv on cluster cluster_2S_2R 
TO stg.mart_mdlp_general_report_on_remaining_items AS
SELECT * FROM kafka.mdlp_general_report_on_remaining_items;

DROP table stg.mart_mdlp_general_report_on_remaining_items on cluster cluster_2S_2R

create table stg.mart_mdlp_general_report_on_remaining_items on cluster cluster_2S_2R
(
	uuid_report text,
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
	remains_in_the_market_units text, 
	remains_before_the_input_in_th_units text, 
	general_residues_units text, 
	source_of_financing text, 
	data_update_date text, 
	remains_in_the_market_excluding_705_unitary_enterprise text, 
	shipped text, 
	type_report text, 
	date_to text, 
	create_dttm text,
	deleted_flag bool
)
engine = ReplacingMergeTree()
order by (uuid_report, gtin, tin_to_the_issuer, tin_of_the_participant, deleted_flag)

select tin_to_the_issuer, tin_of_the_participant, gtin, count (*) from cluster('cluster_2S_2R', 'stg', 'mart_mdlp_general_report_on_remaining_items')
group by tin_to_the_issuer, tin_of_the_participant, gtin

select * from cluster('cluster_2S_2R', 'stg', 'mart_mdlp_general_report_on_remaining_items')
where tin_to_the_issuer = '2226002532' and tin_of_the_participant = '7734722725' and gtin = '4603679000324'
