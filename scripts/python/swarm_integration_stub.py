def process_local_swarm_data(node_data: dict) -> bool:
    """Processes data received from a local swarm node and performs initial aggregation."""
    if not isinstance(node_data, dict) or 'node_id' not in node_data or 'status' not in node_data or 'timestamp' not in node_data:
        print("Validation Error: Input data must be a dictionary containing 'node_id', 'status', and 'timestamp'.")
        return False
    
    # Validate timestamp and check for staleness
    try:
        timestamp_str = node_data['timestamp']
        import datetime
        data_timestamp = datetime.datetime.fromisoformat(timestamp_str)
        if (datetime.datetime.now() - data_timestamp).total_seconds() > 3600:
             print("Validation Warning: Data appears stale (older than 1 hour).")
        
    except (ValueError, TypeError):
        print("Validation Error: Timestamp must be a valid ISO format string.")
        return False
    
    # Minimal aggregation: store node status by ID
    # In a real scenario, this would update a shared context/database
    aggregated_data = {node_data['node_id']: node_data['status']}
    print(f"INFO: Successfully validated data for Node {node_data['node_id']}. Status: {node_data['status']}. Aggregated {len(aggregated_data)} records.")
    
    # ACTION: Log processed data payload to the local telemetry buffer.
    print(f"TELEMETRY_LOG: Payload processed for {node_data['node_id']} at {datetime.datetime.now().isoformat()}")
    return True