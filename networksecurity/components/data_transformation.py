import sys
import os
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder, StandardScaler, LabelEncoder, PowerTransformer
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.base import BaseEstimator, TransformerMixin
from networksecurity.constant.training_pipeline import TARGET_COLUMN
from networksecurity.entity.artifact_entity import DataTransformationArtifact, DataValidationArtifact
from networksecurity.entity.config_entity import DataTransformationConfig
from networksecurity.exception.exception import NetworkSecurityException
from networksecurity.logging.logger import logging
from networksecurity.utils.main_utils.utils import save_numpy_array_data, save_object


class LogFeatureAdder(BaseEstimator, TransformerMixin):
    def __init__(self, features):
        self.features = features

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        X = X.copy()
        for feature in self.features:
            if feature in X.columns:
                X[f"{feature}_log"] = np.log1p(X[feature])
        return X


class DataPreprocessor:
    def __init__(self, validation_artifact: DataValidationArtifact, config: DataTransformationConfig):
        try:
            self.validation_artifact = validation_artifact
            self.config = config
        except Exception as e:
            raise NetworkSecurityException(e, sys)

    @staticmethod
    def load_data(file_path) -> pd.DataFrame:
        try:
            return pd.read_csv(file_path)
        except Exception as e:
            raise NetworkSecurityException(e, sys)

    def construct_transformer(self, df: pd.DataFrame) -> ColumnTransformer:
        try:
            logging.info("Creating transformation pipeline...")

            label_columns = [TARGET_COLUMN, 'label']
            numeric_features = df.select_dtypes(include=['int64', 'float64']).columns.difference(label_columns).tolist()
            categorical_features = df.select_dtypes(include=['object']).columns.difference(label_columns).tolist()

            skew_threshold = 1.0
            skewed_numeric = [col for col in numeric_features if abs(df[col].skew()) > skew_threshold]
            regular_numeric = list(set(numeric_features) - set(skewed_numeric))

            logging.info(f"Highly skewed numeric features: {skewed_numeric}")
            logging.info(f"Normal numeric features: {regular_numeric}")

            skewed_pipeline = Pipeline([
                ("imputer", SimpleImputer(strategy="mean")),
                ("power_transform", PowerTransformer(method="yeo-johnson")),
                ("scale", StandardScaler())
            ])

            normal_pipeline = Pipeline([
                ("imputer", SimpleImputer(strategy="mean")),
                ("scale", StandardScaler())
            ])

            categorical_pipeline = Pipeline([
                ("imputer", SimpleImputer(strategy="most_frequent")),
                ("encode", OneHotEncoder(handle_unknown="ignore"))
            ])

            full_transformer = ColumnTransformer([
                ("skewed_numeric", skewed_pipeline, skewed_numeric),
                ("normal_numeric", normal_pipeline, regular_numeric),
                # ("categorical", categorical_pipeline, categorical_features)  # Uncomment if needed
            ])

            return full_transformer

        except Exception as e:
            raise NetworkSecurityException(e, sys)

    def execute_transformation(self) -> DataTransformationArtifact:
        try:
            logging.info("Starting transformation on input datasets...")

            train_df = self.load_data(self.validation_artifact.valid_train_file_path)
            test_df = self.load_data(self.validation_artifact.valid_test_file_path)

            X_train = train_df.drop(columns=[TARGET_COLUMN])
            y_train = train_df[TARGET_COLUMN]

            X_test = test_df.drop(columns=[TARGET_COLUMN])
            y_test = test_df[TARGET_COLUMN]

            encoder = LabelEncoder()
            y_train_encoded = encoder.fit_transform(y_train)
            y_test_encoded = encoder.transform(y_test)

            save_object("final_model/label_encoder.pkl", encoder)

            transformer = self.construct_transformer(X_train)

            fitted_transformer = transformer.fit(X_train)
            X_train_processed = fitted_transformer.transform(X_train)
            X_test_processed = fitted_transformer.transform(X_test)

            if hasattr(X_train_processed, "toarray"):
                X_train_processed = X_train_processed.toarray()
            if hasattr(X_test_processed, "toarray"):
                X_test_processed = X_test_processed.toarray()

            train_data = np.c_[X_train_processed, y_train_encoded.reshape(-1, 1)]
            test_data = np.c_[X_test_processed, y_test_encoded.reshape(-1, 1)]

            save_numpy_array_data(self.config.transformed_train_file_path, train_data)
            save_numpy_array_data(self.config.transformed_test_file_path, test_data)
            save_object(self.config.transformed_object_file_path, fitted_transformer)
            save_object("final_model/preprocessor.pkl", fitted_transformer)

            return DataTransformationArtifact(
                transformed_object_file_path=self.config.transformed_object_file_path,
                transformed_train_file_path=self.config.transformed_train_file_path,
                transformed_test_file_path=self.config.transformed_test_file_path,
            )

        except Exception as e:
            raise NetworkSecurityException(e, sys)
