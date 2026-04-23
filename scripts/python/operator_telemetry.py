import time
import random
from scripts.python.lumina_logger import get_logger

logger = get_logger("OperatorTelemetry")

def collect_operator_metrics() -> dict:
    """Collects basic operational metrics for the Grounding Layer."""
    logger.info("Collecting basic operator telemetry metrics.")
    
    # Simulate dynamic metric collection
    return {
        "timestamp": time.time(),
        "status": "operational", 
        "cpu_load_percent": round(random.uniform(10.0, 50.0), 2), 
        "network_latency_ms": round(random.uniform(5.0, 50.0), 2)
    }

def process_telemetry_data(data: dict) -> bool:
    """Processes collected telemetry data and logs anomalies."""
    if data.get("status") == "operational":
        logger.info("Telemetry data processed successfully.")
        return True
    logger.error(f"Telemetry data processing failed: {data}")
    return False