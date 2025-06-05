from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
import sys
import os

# Ensure base project path is included
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from networksecurity.components.data_ingestion import DataIngestion
from networksecurity.components.data_validation import DataValidation
from networksecurity.components.data_transformation import DataTransformation

from networksecurity.entity.config_entity import (
    TrainingPipelineConfig, 
    DataIngestionConfig, 
    DataValidationConfig, 
    DataTransformationConfig
)

from networksecurity.exception.exception import NetworkSecurityException
from networksecurity.logging.logger import logging

# Shared dictionary for intermediate artifacts
artifacts = {}

def run_data_ingestion():
    training_config = TrainingPipelineConfig()
    data_ingestion_config = DataIngestionConfig(training_config)
    ingestion = DataIngestion(data_ingestion_config)
    logging.info("Starting Data Ingestion")
    artifacts['data_ingestion'] = ingestion.initiate_data_ingestion()
    logging.info("Data Ingestion Completed")

def run_data_validation():
    training_config = TrainingPipelineConfig()
    data_validation_config = DataValidationConfig(training_config)
    validation = DataValidation(artifacts['data_ingestion'], data_validation_config)
    logging.info("Starting Data Validation")
    artifacts['data_validation'] = validation.initiate_data_validation()
    logging.info("Data Validation Completed")

def run_data_transformation():
    training_config = TrainingPipelineConfig()
    data_transformation_config = DataTransformationConfig(training_config)
    transformation = DataTransformation(artifacts['data_validation'], data_transformation_config)
    logging.info("Starting Data Transformation")
    artifacts['data_transformation'] = transformation.initiate_data_transformation()
    logging.info("Data Transformation Completed")

default_args = {
    'start_date': datetime(2024, 1, 1),
    'catchup': False,
    'retries': 1
}

with DAG(
    dag_id='ml_data_pipeline',
    schedule_interval='@weekly',
    default_args=default_args,
    description='Airflow DAG for data ingestion, validation, and transformation',
    tags=['ml', 'pipeline', 'airflow']
) as dag:

    task_data_ingestion = PythonOperator(
        task_id='data_ingestion',
        python_callable=run_data_ingestion
    )

    task_data_validation = PythonOperator(
        task_id='data_validation',
        python_callable=run_data_validation
    )

    task_data_transformation = PythonOperator(
        task_id='data_transformation',
        python_callable=run_data_transformation
    )

    task_data_ingestion >> task_data_validation >> task_data_transformation
