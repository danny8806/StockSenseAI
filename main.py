from db import get_connection
from pipeline import run_pipeline

if __name__ == "__main__":
    conn = get_connection()
    run_pipeline(conn)
    print("✅ StockSenseAI pipeline completed")
