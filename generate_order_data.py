import csv
import random
from datetime import datetime, timedelta

def generate_orders(num_orders=2000):
    orders = []
    operations = [
        "Cutting", "Drilling", "Milling", "Turning", "Grinding", "Welding",
        "Assembly", "Testing", "Quality Control", "Packaging", "Shipping"
    ]
    
    # Total time per order: 5 minutes = 300 seconds
    TOTAL_ORDER_TIME = 300
    MAX_OPERATION_TIME = 600  # Maximum 10 minutes per operation
    
    # Generate 2000+ orders
    for i in range(num_orders):
        order_code = f"ORD{i+1:04d}"
        quantity = random.randint(10, 100)
        
        # Generate 4-8 operations per order
        num_operations = random.randint(4, 8)
        remaining_time = TOTAL_ORDER_TIME
        
        for j in range(num_operations):
            operation_id = f"OP{j+1:02d}"
            operation_name = random.choice(operations)
            
            # Generate 2-4 capable machines per operation
            num_machines = random.randint(2, 4)
            capable_machines = [f"M{k}" for k in random.sample(range(1, 46), num_machines)]
            
            # Calculate operation time (distribute remaining time among operations)
            if j == num_operations - 1:  # Last operation gets remaining time
                operation_time = remaining_time
            else:
                # Random time between 30 seconds and min(remaining time, 10 minutes)
                max_time = min(remaining_time - (30 * (num_operations - j - 1)), MAX_OPERATION_TIME)
                operation_time = random.randint(30, max_time)
                remaining_time -= operation_time
            
            # Generate processing times in seconds for each machine
            processing_times = {}
            for machine in capable_machines:
                # Add some variation (±10%) to the base operation time
                variation = random.uniform(0.9, 1.1)
                processing_times[machine] = int(operation_time * variation)
            
            # Convert processing times to string format
            processing_times_str = ";".join([f"{machine}:{time}" for machine, time in processing_times.items()])
            
            orders.append({
                'order_code': order_code,
                'operation_id': operation_id,
                'operation_name': operation_name,
                'quantity': quantity,
                'capable_machines': ','.join(capable_machines),
                'processing_times': processing_times_str,
                'sequence_number': j + 1
            })
    
    return orders

def save_to_csv(orders, filename='orders_data.csv'):
    fieldnames = ['order_code', 'operation_id', 'operation_name', 'quantity', 
                  'capable_machines', 'processing_times', 'sequence_number']
    
    with open(filename, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(orders)

if __name__ == '__main__':
    orders = generate_orders(20)  # Generate 2000 orders
    save_to_csv(orders)
    print(f"Generated {len(orders)} order operations")