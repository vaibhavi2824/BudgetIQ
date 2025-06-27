import pandas as pd
import zipfile
from openpyxl import Workbook
from datetime import datetime
import uuid

def safe_read_excel(filepath, columns):
    """Safely read an Excel file, creating it with default columns if not exists"""
    try:
        return pd.read_excel(filepath, engine='openpyxl')
    except (FileNotFoundError, ValueError, zipfile.BadZipFile):
        print(f"Creating new file: {filepath}")
        df = pd.DataFrame(columns=columns)
        write_to_excel(filepath, df)
        return df

def write_to_excel(filepath, dataframe):
    """Write dataframe to Excel file"""
    dataframe.to_excel(filepath, index=False, engine='openpyxl')

def generate_id():
    """Generate a unique ID"""
    return str(uuid.uuid4())

def get_current_month():
    """Get current month in YYYY-MM format"""
    return datetime.now().strftime('%Y-%m')