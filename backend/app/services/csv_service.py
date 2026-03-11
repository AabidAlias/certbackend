"""
services/csv_service.py
Parses uploaded CSV files and returns validated name/email rows.
"""
import io
import pandas as pd
from typing import List, Tuple

from app.utils.helpers import get_logger

logger = get_logger(__name__)


def parse_csv(file_bytes: bytes) -> List[Tuple[str, str]]:
    """
    Parse a CSV file and return a list of (name, email) tuples.
    
    Expected CSV columns: Name, Email (case-insensitive).
    Skips rows with missing or invalid data.
    """
    try:
        df = pd.read_csv(io.BytesIO(file_bytes))
        # Normalize column names
        df.columns = [col.strip().lower() for col in df.columns]

        if "name" not in df.columns or "email" not in df.columns:
            raise ValueError("CSV must contain 'Name' and 'Email' columns.")

        df = df[["name", "email"]].dropna()
        df["name"] = df["name"].astype(str).str.strip()
        df["email"] = df["email"].astype(str).str.strip().str.lower()

        # Filter out clearly invalid rows
        df = df[df["name"].str.len() > 0]
        df = df[df["email"].str.contains("@")]

        records = list(df.itertuples(index=False, name=None))
        logger.info(f"Parsed {len(records)} valid rows from CSV.")
        return records

    except Exception as e:
        logger.error(f"CSV parsing failed: {e}")
        raise ValueError(f"Failed to parse CSV: {e}")
