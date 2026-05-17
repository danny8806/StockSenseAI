from db import get_connection
from pipeline import run_pipeline

if __name__ == "__main__":
    conn = get_connection()
    stats = run_pipeline(conn, limit=30)
    conn.close()
    print("StockSenseAI pipeline completed")
    print(stats)
