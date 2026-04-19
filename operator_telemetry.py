from scripts.python.lumina_logger import get_logger
from typing import Dict, Any

logger = get_logger("OperatorTelemetry")

def generate_telemetry_report(operator_id: str, metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generates a structured telemetry report for a given operator.
    This function performs basic validation on incoming metrics.
    """
    if not metrics or 'cpu_load' not in metrics:
        logger.warning(f"Incomplete metrics received for operator {operator_id}.")
        return {"status": "ERROR", "message": "Missing required metrics."}
        
    report = {
        "operator_id": operator_id,
        "timestamp": "PLACEHOLDER_TIMESTAMP", # Placeholder for actual time retrieval
        "cpu_load_percent": metrics.get('cpu_load', 0.0),
        "memory_usage_gb": metrics.get('memory', 0.0),
        "status": "OK"
    }
    return report

# Example usage placeholder (will be expanded)
# report = generate_telemetry_report("OP-001", {"cpu_load": 0.65, "memory": 12.4})
# print(report)