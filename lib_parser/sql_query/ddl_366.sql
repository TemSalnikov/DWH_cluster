create database stg on cluster cluster_2S_2R

create database dds on cluster cluster_2S_2R

create database bdm on cluster cluster_2S_2R

create database kafka on cluster cluster_2S_2R

SELECT * FROM system.clusters WHERE cluster = 'cluster_2S_2R'

--drop table stg.mart_fpc_366_drugstor on cluster cluster_2S_2R




create table stg.mart_fpc_366_drugstor on cluster cluster_2S_2R
(
	name text,
	legal_name text,
	inn bigint,
	id bigint,
	address text,
	hash_drugstore text
)
engine = ReplacingMergeTree()
order by (hash_drugstore)

alter TABLE stg.mart_fpc_366_drugstor on cluster cluster_2S_2R
add column hash_drugstore_addr text;

alter TABLE stg.mart_fpc_366_drugstor on cluster cluster_2S_2R
MODIFY ORDER BY (hash_drugstore_addr)

drop table kafka.fpc_366_drugstor on cluster cluster_2S_2R

create table kafka.fpc_366_drugstor on cluster cluster_2S_2R
(
	name text,
	legal_name text,
	inn bigint,
	id bigint,
	address text,
	hash_drugstore_addr text,
	hash_drugstore text
)
engine = Kafka()
SETTINGS
    kafka_broker_list = '192.168.14.235:9091, 192.168.14.235:9092, 192.168.14.235:9093',
    kafka_topic_list = 'fpc_366_table_drugstor',
    kafka_group_name = 'clickhouse',
    kafka_format = 'JSONColumns',
    kafka_num_consumers = 1;

alter TABLE kafka.fpc_366_drugstor on cluster cluster_2S_2R
add column hash_drugstore_addr text;



drop VIEW kafka.fpc_366_drugstor_mv on cluster cluster_2S_2R

CREATE MATERIALIZED VIEW kafka.fpc_366_drugstor_mv on cluster cluster_2S_2R TO stg.mart_fpc_366_drugstor AS
SELECT * FROM kafka.fpc_366_drugstor;

select * from stg.mart_fpc_366_drugstor

--
drop table stg.mart_fpc_366_product on cluster cluster_2S_2R

create table stg.mart_fpc_366_product  on cluster cluster_2S_2R
(
	name text,
	id bigint,
	manufacturer text,
	hash_product text
)
engine = ReplacingMergeTree()
order by (hash_product)

truncate table if exists stg.mart_fpc_366_report on cluster cluster_2S_2R

drop table kafka.fpc_366_product on cluster cluster_2S_2R

create table kafka.fpc_366_product on cluster cluster_2S_2R
(
	name text,
	id bigint,
	manufacturer text,
	hash_product text
)
engine = Kafka()
SETTINGS
    kafka_broker_list = '192.168.14.235:9091, 192.168.14.235:9092, 192.168.14.235:9093',
    kafka_topic_list = 'fpc_366_table_product',
    kafka_group_name = 'clickhouse',
    kafka_format = 'JSONColumns',
    kafka_num_consumers = 1;

drop VIEW kafka.fpc_366_product_mv on cluster cluster_2S_2R

CREATE MATERIALIZED VIEW kafka.fpc_366_product_mv on cluster cluster_2S_2R TO stg.mart_fpc_366_product AS
SELECT * FROM kafka.fpc_366_product;

--
drop table stg.mart_fpc_366_supplier on cluster cluster_2S_2R

truncate table stg.mart_fpc_366_report on cluster cluster_2S_2R 

create table stg.mart_fpc_366_supplier on cluster cluster_2S_2R
(
	name text,
	legal_name text,
	inn bigint,
	id bigint,
	address text,
	hash_supplier text
)
engine = ReplacingMergeTree()
order by (hash_suplier)

drop table kafka.fpc_366_supplier on cluster cluster_2S_2R

create table kafka.fpc_366_supplier on cluster cluster_2S_2R
(
	name text,
	legal_name text,
	inn bigint,
	id bigint,
	address text,
	hash_supplier text
)
engine = Kafka()
SETTINGS
    kafka_broker_list = '192.168.14.235:9091, 192.168.14.235:9092, 192.168.14.235:9093',
    kafka_topic_list = 'fpc_366_table_suplier',
    kafka_group_name = 'clickhouse',
    kafka_format = 'JSONColumns',
    kafka_num_consumers = 1;

drop VIEW stg.fpc_366_suplier_mv on cluster cluster_2S_2R

CREATE MATERIALIZED VIEW kafka.fpc_366_supplier_mv on cluster cluster_2S_2R TO stg.mart_fpc_366_supplier AS
SELECT * FROM kafka.fpc_366_supplier;

--
drop table stg.mart_fpc_366_report on cluster cluster_2S_2R

create table stg.mart_fpc_366_report on cluster cluster_2S_2R
(
	uuid_report text,
	period text,
	quantity text,
	total_cost text,
	hash_drugstore text,
	hash_supplier text,
	hash_product text,
	processed_dttm text
)
engine = ReplacingMergeTree()
order by (uuid_report)

alter TABLE stg.mart_fpc_366_report on cluster cluster_2S_2R
add column hash_drugstore_addr text;

drop table kafka.fpc_366_report on cluster cluster_2S_2R

create table kafka.fpc_366_report on cluster cluster_2S_2R
(
	uuid_report text,
	name_report text,
	name_pharm_chain text,
	period text,
	quantity text,
	total_cost text,
	hash_drugstore text,
	hash_drugstore_addr text,
	hash_supplier text,
	hash_product text,
	processed_dttm text
)
engine = Kafka()
SETTINGS
    kafka_broker_list = '192.168.14.235:9091, 192.168.14.235:9092, 192.168.14.235:9093',
    kafka_topic_list = 'fpc_366_table_report',
    kafka_group_name = 'clickhouse',
    kafka_format = 'JSONColumns',
    kafka_max_block_size = 10485760,
    kafka_poll_max_batch_size = 10485760,
    kafka_handle_error_mode = 'stream',
    kafka_num_consumers = 1;

alter TABLE kafka.fpc_366_report on cluster cluster_2S_2R
add column hash_drugstore_addr text;

drop VIEW kafka.fpc_366_report_mv on cluster cluster_2S_2R

CREATE MATERIALIZED VIEW kafka.fpc_366_report_mv  on cluster cluster_2S_2R TO stg.mart_fpc_366_report AS
SELECT * FROM kafka.fpc_366_report;

select hash_drugstore_addr, count(*) from cluster('cluster_2S_2R', 'stg', 'mart_fpc_366_drugstor')
group by hash_drugstore_addr
having count(*) > 1

select * from cluster('cluster_2S_2R', 'stg', 'mart_fpc_366_supplier' ) 

select * from cluster('cluster_2S_2R', 'stg', 'mart_fpc_366_product')

select * from cluster('cluster_2S_2R', 'stg', 'mart_fpc_366_report')  
where hash_supplier != ''

truncate table stg.mart_fpc_366_report on cluster cluster_2S_2R

truncate table stg.mart_fpc_366_drugstor on cluster cluster_2S_2R
