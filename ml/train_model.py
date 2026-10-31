"""
Train Decision Tree models for student performance prediction.
Run this once to generate the saved model files.
"""

import pandas as pd
import numpy as np
from sklearn.tree import DecisionTreeClassifier
from sklearn.preprocessing import LabelEncoder
import pickle
import os

def train_models():
    # Load dataset
    df = pd.read_csv(os.path.join(os.path.dirname(__file__), 'sample_data.csv'))
    
    # Encode categorical columns (fit on pre-defined lists to cover all potential input categories)
    le_medical = LabelEncoder().fit(['No', 'Yes'])
    df['medical_leave_enc'] = le_medical.transform(df['medical_leave'])
    
    le_tenth_board = LabelEncoder().fit(['CBSE', 'ICSE', 'State Board', 'Other'])
    df['tenth_board_enc'] = le_tenth_board.transform(df['tenth_board'])
    
    le_twelfth_board = LabelEncoder().fit(['CBSE', 'ICSE', 'State Board', 'Diploma', 'Other'])
    df['twelfth_board_enc'] = le_twelfth_board.transform(df['twelfth_board'])
    
    le_school_type = LabelEncoder().fit(['Government', 'Private', 'Aided', 'International'])
    df['school_type_enc'] = le_school_type.transform(df['school_type'])
    
    le_school_location = LabelEncoder().fit(['Urban', 'Rural', 'Semi-Urban'])
    df['school_location_enc'] = le_school_location.transform(df['school_location'])
    
    le_own_laptop = LabelEncoder().fit(['No', 'Yes'])
    df['own_laptop_enc'] = le_own_laptop.transform(df['own_laptop'])
    
    le_smartphone = LabelEncoder().fit(['No', 'Yes'])
    df['smartphone_enc'] = le_smartphone.transform(df['smartphone'])
    
    le_internet = LabelEncoder().fit(['No', 'Yes'])
    df['internet_enc'] = le_internet.transform(df['internet'])
    
    # Target encoders
    le_result = LabelEncoder()
    df['result_enc'] = le_result.fit_transform(df['result'])  # Fail=0, Pass=1
    
    le_risk = LabelEncoder()
    df['risk_enc'] = le_risk.fit_transform(df['risk_level'])  # High=0, Low=1, Medium=2
    
    # Features
    features = [
        'attendance', 'internal_marks', 'study_hours', 'dbms_marks', 'java_marks', 'prev_sem_percentage', 'medical_leave_enc',
        'tenth_board_enc', 'tenth_percentage', 'twelfth_board_enc', 'twelfth_percentage', 'school_type_enc', 'school_location_enc',
        'own_laptop_enc', 'laptop_years', 'smartphone_enc', 'internet_enc', 'programming_experience'
    ]
    
    X = df[features]
    
    # Train Pass/Fail model
    y_result = df['result_enc']
    model_result = DecisionTreeClassifier(max_depth=5, random_state=42)
    model_result.fit(X, y_result)
    
    # Train Risk Level model
    y_risk = df['risk_enc']
    model_risk = DecisionTreeClassifier(max_depth=5, random_state=42)
    model_risk.fit(X, y_risk)
    
    # Save models
    model_dir = os.path.dirname(__file__)
    with open(os.path.join(model_dir, 'model_result.pkl'), 'wb') as f:
        pickle.dump(model_result, f)
    with open(os.path.join(model_dir, 'model_risk.pkl'), 'wb') as f:
        pickle.dump(model_risk, f)
    
    # Save encoders
    encoders = {
        'le_result': le_result,
        'le_risk': le_risk,
        'le_medical': le_medical,
        'le_tenth_board': le_tenth_board,
        'le_twelfth_board': le_twelfth_board,
        'le_school_type': le_school_type,
        'le_school_location': le_school_location,
        'le_own_laptop': le_own_laptop,
        'le_smartphone': le_smartphone,
        'le_internet': le_internet,
        'feature_names': features
    }
    with open(os.path.join(model_dir, 'encoders.pkl'), 'wb') as f:
        pickle.dump(encoders, f)
    
    print("Models trained and saved successfully!")
    print(f"   Result classes: {le_result.classes_}")
    print(f"   Risk classes:   {le_risk.classes_}")
    return model_result, model_risk, encoders

if __name__ == '__main__':
    train_models()
