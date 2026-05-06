"""
Uploads composite_scores.parquet to the QuantConnect Object Store.

Run this from the QC Research environment (Jupyter notebook terminal), or
copy-paste into a QC Research notebook cell.

The algorithm reads the file from Object Store key: narrative/composite_scores.parquet
"""

PARQUET_PATH = "composite_scores.parquet"   # local path in QC Research environment
OBJECT_STORE_KEY = "narrative/composite_scores.parquet"

with open(PARQUET_PATH, "rb") as f:
    data = f.read()

qb.object_store.save_bytes(OBJECT_STORE_KEY, data)
print(f"Uploaded {len(data):,} bytes → {OBJECT_STORE_KEY}")
