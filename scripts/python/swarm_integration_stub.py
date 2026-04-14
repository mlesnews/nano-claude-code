def process_local_swarm_data(node_data: dict) -> bool:
    """Processes data received from a local swarm node."""
    if not isinstance(node_data, dict) or 'node_id' not in node_data or 'status' not in node_data:
        print("Validation Error: Input data must be a dictionary containing 'node_id' and 'status'.")
        return False
    
    node_id = node_data['node_id']
    status = node_data['status']
    
    print(f"INFO: Successfully validated data for Node {node_id}. Status: {status}")
    # Future implementation: Integrate with consensus/health checking service
    return True